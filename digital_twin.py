"""
I.R.I.S. — Digital Twin (Physics Model)
========================================
A 6-DOF rigid body flight dynamics model serving as the base world model
for the QDRL-AP architecture. Implements:

  - 6-DOF rigid body flight dynamics (3 translation + 3 rotation)
  - Aerodynamics: lift, drag, air density, AoA effects, stall modelling
  - Propulsion: turbofan thrust curves, fuel burn, engine lag
  - Control surfaces: ailerons, elevator, rudder with actuator delays
  - Numerical integration: Runge-Kutta 4 (RK4)
  - Sensor & avionics layer: GNSS (with noise/jamming), INS drift,
    Kalman filter fusion, pitot tube, barometric altimeter, IMU

Dependencies: numpy, scipy (standard scientific Python stack)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Tuple


# =============================================================================
# CONSTANTS
# =============================================================================

G          = 9.81        # gravitational acceleration (m/s²)
R_AIR      = 287.05      # specific gas constant for air (J/kg·K)
GAMMA_AIR  = 1.4         # ratio of specific heats
RHO_SL     = 1.225       # air density at sea level (kg/m³)
T_SL       = 288.15      # temperature at sea level (K)
LAPSE_RATE = 0.0065      # temperature lapse rate (K/m)
P_SL       = 101325.0    # pressure at sea level (Pa)


# =============================================================================
# AIRCRAFT PARAMETERS  (representative narrow-body twin-turbofan)
# =============================================================================

@dataclass
class AircraftParams:
    # Mass & geometry
    mass_empty:    float = 42000.0   # kg
    fuel_mass:     float = 15000.0   # kg (initial)
    wing_area:     float = 122.6     # m²
    wing_span:     float = 34.1      # m
    mac:           float = 3.6       # mean aerodynamic chord (m)

    # Aerodynamic coefficients (baseline)
    CL_alpha:      float = 5.5       # lift curve slope (per rad)
    CL_0:          float = 0.28      # zero-AoA lift coefficient
    CD_0:          float = 0.024     # zero-lift drag coefficient
    CD_k:          float = 0.042     # induced drag factor (1/pi/e/AR)
    CL_max:        float = 1.6       # stall lift coefficient
    alpha_stall:   float = 0.28      # stall angle of attack (rad, ~16°)

    # Moments of inertia (kg·m²)
    Ixx:           float = 1.0e6     # roll
    Iyy:           float = 5.0e6     # pitch
    Izz:           float = 5.5e6     # yaw
    Ixz:           float = 1.0e4     # cross-product term

    # Control surface effectiveness (per rad deflection)
    CL_de:         float = 0.44      # elevator pitch moment
    CL_da:         float = 0.08      # aileron roll moment
    CL_dr:         float = 0.06      # rudder yaw moment

    # Actuator limits & delays
    max_elevator:  float = 0.436     # rad (~25°)
    max_aileron:   float = 0.349     # rad (~20°)
    max_rudder:    float = 0.436     # rad (~25°)
    actuator_tau:  float = 0.1       # actuator time constant (s)

    # Propulsion
    thrust_max_sl: float = 2 * 120000.0  # N (two engines, sea level static)
    tsfc:          float = 1.8e-5    # thrust-specific fuel consumption (kg/N/s)
    engine_tau:    float = 2.0       # engine lag time constant (s)


# =============================================================================
# SECTION 1 — ATMOSPHERE MODEL
# International Standard Atmosphere (ISA), troposphere only
# =============================================================================

def isa_atmosphere(altitude_m: float) -> Tuple[float, float, float]:
    """
    Returns (temperature K, pressure Pa, density kg/m³) at given altitude.
    Valid for troposphere (0–11000 m). Capped at 11 km for simplicity.
    """
    alt = min(max(altitude_m, 0.0), 11000.0)
    T   = T_SL - LAPSE_RATE * alt
    P   = P_SL * (T / T_SL) ** (G / (LAPSE_RATE * R_AIR))
    rho = P / (R_AIR * T)
    return T, P, rho


def speed_of_sound(altitude_m: float) -> float:
    T, _, _ = isa_atmosphere(altitude_m)
    return np.sqrt(GAMMA_AIR * R_AIR * T)


# =============================================================================
# SECTION 2 — AERODYNAMICS
# Lift, drag, moments including stall and AoA effects
# =============================================================================

def compute_aerodynamics(
    state: 'AircraftState',
    controls: 'ControlInputs',
    params: AircraftParams
) -> Tuple[float, float, float, float, float, float]:
    """
    Computes aerodynamic forces (Fx, Fy, Fz) and moments (Mx, My, Mz)
    in body frame.

    Returns: (Fx, Fy, Fz, Mx_aero, My_aero, Mz_aero)
    """
    _, _, rho = isa_atmosphere(state.position[2])

    # Airspeed magnitude
    V = np.linalg.norm(state.velocity_body)
    V = max(V, 1.0)   # avoid division by zero at rest

    q_dyn = 0.5 * rho * V**2   # dynamic pressure (Pa)
    S     = params.wing_area
    b     = params.wing_span
    c     = params.mac

    # Angle of attack and sideslip
    u, v, w = state.velocity_body
    alpha = np.arctan2(w, max(u, 0.1))   # angle of attack (rad)
    beta  = np.arcsin(v / V)              # sideslip angle (rad)

    # ── Lift coefficient with stall modelling ────────────────────────────────
    if abs(alpha) < params.alpha_stall:
        CL = params.CL_0 + params.CL_alpha * alpha
    else:
        # Post-stall: rapid CL drop
        sign_a = np.sign(alpha)
        excess = abs(alpha) - params.alpha_stall
        CL = params.CL_max * sign_a * max(0.0, 1.0 - 3.0 * excess)

    CL = np.clip(CL, -params.CL_max, params.CL_max)

    # Elevator contribution to lift
    CL += params.CL_de * controls.elevator

    # ── Drag coefficient (parabolic polar) ───────────────────────────────────
    CD = params.CD_0 + params.CD_k * CL**2

    # ── Side force ───────────────────────────────────────────────────────────
    CY = -0.8 * beta + params.CL_dr * controls.rudder

    # ── Forces in wind frame → body frame ────────────────────────────────────
    L_force = q_dyn * S * CL
    D_force = q_dyn * S * CD
    Y_force = q_dyn * S * CY

    # Rotate lift and drag to body frame
    ca, sa = np.cos(alpha), np.sin(alpha)
    Fx = -D_force * ca + L_force * sa
    Fz = -D_force * sa - L_force * ca
    Fy =  Y_force

    # ── Moments ──────────────────────────────────────────────────────────────
    Cm_pitch  = -0.5 * alpha + params.CL_de * controls.elevator * 1.2
    Cl_roll   =  params.CL_da * controls.aileron
    Cn_yaw    = -0.15 * beta  + params.CL_dr * controls.rudder

    Mx_aero = q_dyn * S * b * Cl_roll    # roll moment
    My_aero = q_dyn * S * c * Cm_pitch   # pitch moment
    Mz_aero = q_dyn * S * b * Cn_yaw    # yaw moment

    return Fx, Fy, Fz, Mx_aero, My_aero, Mz_aero


# =============================================================================
# SECTION 3 — PROPULSION MODEL
# Turbofan thrust curves, fuel burn, engine lag dynamics
# =============================================================================

def compute_thrust(
    throttle_cmd: float,
    engine_state: float,
    altitude_m: float,
    mach: float,
    params: AircraftParams,
    dt: float
) -> Tuple[float, float, float]:
    """
    Returns (thrust N, new_engine_state, fuel_burn_rate kg/s).

    engine_state: current throttle level (0–1), lags behind command
    Thrust falls with altitude (density ratio) and rises slightly with speed
    (ram recovery) up to ~Mach 0.85.
    """
    # Engine lag — first-order lag filter
    tau = params.engine_tau
    new_engine_state = engine_state + (throttle_cmd - engine_state) * (dt / tau)
    new_engine_state = np.clip(new_engine_state, 0.0, 1.0)

    # Altitude correction (density ratio to power 0.9)
    _, _, rho = isa_atmosphere(altitude_m)
    density_ratio = rho / RHO_SL

    # Ram recovery (slight thrust increase with Mach up to ~0.85)
    ram_factor = 1.0 + 0.15 * min(mach, 0.85)

    thrust = (params.thrust_max_sl
              * new_engine_state
              * (density_ratio ** 0.9)
              * ram_factor)

    fuel_burn = params.tsfc * thrust   # kg/s

    return thrust, new_engine_state, fuel_burn


# =============================================================================
# SECTION 4 — STATE & CONTROLS DATACLASSES
# =============================================================================

@dataclass
class AircraftState:
    # Position in NED frame (m): North, East, Down (-altitude)
    position:      np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, -8000.0]))

    # Velocity in body frame (m/s): forward (u), lateral (v), vertical (w)
    velocity_body: np.ndarray = field(default_factory=lambda: np.array([230.0, 0.0, 0.0]))

    # Euler angles (rad): roll (phi), pitch (theta), yaw (psi)
    attitude:      np.ndarray = field(default_factory=lambda: np.array([0.0, 0.02, 0.0]))

    # Angular rates in body frame (rad/s): p (roll), q (pitch), r (yaw)
    angular_rates: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.0]))

    # Fuel mass remaining (kg)
    fuel_mass:     float = 15000.0

    # Engine throttle state (0–1, lagged)
    engine_state:  float = 0.75

    # Simulation time (s)
    time:          float = 0.0


@dataclass
class ControlInputs:
    throttle: float = 0.75    # 0–1
    elevator: float = 0.0     # rad, + nose up
    aileron:  float = 0.0     # rad, + right wing down
    rudder:   float = 0.0     # rad, + nose right

    def clamp(self, params: AircraftParams) -> 'ControlInputs':
        return ControlInputs(
            throttle = np.clip(self.throttle, 0.0, 1.0),
            elevator = np.clip(self.elevator, -params.max_elevator, params.max_elevator),
            aileron  = np.clip(self.aileron,  -params.max_aileron,  params.max_aileron),
            rudder   = np.clip(self.rudder,   -params.max_rudder,   params.max_rudder),
        )


# =============================================================================
# SECTION 5 — 6-DOF EQUATIONS OF MOTION
# =============================================================================

def rotation_matrix(phi: float, theta: float, psi: float) -> np.ndarray:
    """Body-to-NED rotation matrix (ZYX Euler convention)."""
    cp, sp = np.cos(phi),   np.sin(phi)
    ct, st = np.cos(theta), np.sin(theta)
    cy, sy = np.cos(psi),   np.sin(psi)

    return np.array([
        [ct*cy,               ct*sy,              -st   ],
        [sp*st*cy - cp*sy,    sp*st*sy + cp*cy,    sp*ct],
        [cp*st*cy + sp*sy,    cp*st*sy - sp*cy,    cp*ct],
    ])


def euler_kinematics(phi: float, theta: float,
                     p: float, q: float, r: float) -> np.ndarray:
    """
    Euler angle rates from angular rates.
    Returns [phi_dot, theta_dot, psi_dot].
    """
    ct = np.cos(theta)
    ct = ct if abs(ct) > 1e-6 else 1e-6   # avoid gimbal lock singularity
    tp = np.tan(theta)

    phi_dot   = p + (q * np.sin(phi) + r * np.cos(phi)) * tp
    theta_dot = q * np.cos(phi) - r * np.sin(phi)
    psi_dot   = (q * np.sin(phi) + r * np.cos(phi)) / ct

    return np.array([phi_dot, theta_dot, psi_dot])


def equations_of_motion(
    state: AircraftState,
    controls: ControlInputs,
    params: AircraftParams,
    dt: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    """
    Computes state derivatives for RK4 integration.

    Returns:
        pos_dot        (3,) NED position rates
        vel_dot        (3,) body velocity rates
        attitude_dot   (3,) Euler angle rates
        omega_dot      (3,) angular acceleration rates
        fuel_dot       scalar fuel burn rate (kg/s)
        new_eng_state  updated engine throttle state
    """
    phi, theta, psi = state.attitude
    p, q, r         = state.angular_rates
    u, v, w         = state.velocity_body
    alt             = -state.position[2]   # altitude (positive up)

    total_mass = params.mass_empty + state.fuel_mass
    V          = np.linalg.norm(state.velocity_body)
    a          = speed_of_sound(alt)
    mach       = V / max(a, 1.0)

    # ── Controls clamped ─────────────────────────────────────────────────────
    ctrl = controls.clamp(params)

    # ── Thrust ───────────────────────────────────────────────────────────────
    thrust, new_eng, fuel_burn = compute_thrust(
        ctrl.throttle, state.engine_state, alt, mach, params, dt
    )

    # ── Aerodynamic forces & moments ─────────────────────────────────────────
    Fx_a, Fy_a, Fz_a, Mx_a, My_a, Mz_a = compute_aerodynamics(
        state, ctrl, params
    )

    # ── Gravity in body frame ─────────────────────────────────────────────────
    Fx_g = -total_mass * G * np.sin(theta)
    Fy_g =  total_mass * G * np.cos(theta) * np.sin(phi)
    Fz_g =  total_mass * G * np.cos(theta) * np.cos(phi)

    # ── Total forces ──────────────────────────────────────────────────────────
    Fx = Fx_a + Fx_g + thrust
    Fy = Fy_a + Fy_g
    Fz = Fz_a + Fz_g

    # ── Translational accelerations (body frame) ──────────────────────────────
    u_dot = Fx / total_mass - q * w + r * v
    v_dot = Fy / total_mass - r * u + p * w
    w_dot = Fz / total_mass - p * v + q * u

    # ── Rotational dynamics (Euler's equations with Ixz cross term) ───────────
    Ixx, Iyy, Izz, Ixz = params.Ixx, params.Iyy, params.Izz, params.Ixz
    Gamma = Ixx * Izz - Ixz**2

    p_dot = (Izz * Mx_a + Ixz * Mz_a
             - (Izz * (Izz - Iyy) + Ixz**2) * q * r
             + Ixz * (Ixx - Iyy + Izz) * p * q) / Gamma

    q_dot = (My_a - (Ixx - Izz) * p * r - Ixz * (p**2 - r**2)) / Iyy

    r_dot = (Ixx * Mz_a + Ixz * Mx_a
             + (Ixx * (Ixx - Iyy) + Ixz**2) * p * q
             - Ixz * (Ixx - Iyy + Izz) * q * r) / Gamma

    # ── Position rates (NED) ──────────────────────────────────────────────────
    R    = rotation_matrix(phi, theta, psi)
    vNED = R.T @ np.array([u, v, w])
    pos_dot = vNED

    # ── Euler angle rates ─────────────────────────────────────────────────────
    att_dot = euler_kinematics(phi, theta, p, q, r)

    return (
        pos_dot,
        np.array([u_dot, v_dot, w_dot]),
        att_dot,
        np.array([p_dot, q_dot, r_dot]),
        fuel_burn,
        new_eng,
    )


# =============================================================================
# SECTION 6 — RK4 INTEGRATOR
# =============================================================================

def rk4_step(
    state: AircraftState,
    controls: ControlInputs,
    params: AircraftParams,
    dt: float
) -> AircraftState:
    """
    One Runge-Kutta 4th order integration step.
    Integrates position, velocity, attitude, angular rates, fuel.
    """
    def derivs(s: AircraftState):
        return equations_of_motion(s, controls, params, dt)

    def state_add(s: AircraftState, scale: float,
                  pd, vd, ad, od, fd, _) -> AircraftState:
        ns = AircraftState()
        ns.position      = s.position      + scale * pd
        ns.velocity_body = s.velocity_body + scale * vd
        ns.attitude      = s.attitude      + scale * ad
        ns.angular_rates = s.angular_rates + scale * od
        ns.fuel_mass     = max(s.fuel_mass - scale * fd * dt, 0.0)
        ns.engine_state  = s.engine_state
        ns.time          = s.time
        return ns

    k1 = derivs(state)
    s2 = state_add(state, dt / 2, *k1)
    k2 = derivs(s2)
    s3 = state_add(state, dt / 2, *k2)
    k3 = derivs(s3)
    s4 = state_add(state, dt, *k3)
    k4 = derivs(s4)

    pd1, vd1, ad1, od1, fd1, eng1 = k1
    pd2, vd2, ad2, od2, fd2, eng2 = k2
    pd3, vd3, ad3, od3, fd3, eng3 = k3
    pd4, vd4, ad4, od4, fd4, eng4 = k4

    new_state = AircraftState()
    new_state.position      = state.position      + (dt / 6) * (pd1 + 2*pd2 + 2*pd3 + pd4)
    new_state.velocity_body = state.velocity_body + (dt / 6) * (vd1 + 2*vd2 + 2*vd3 + vd4)
    new_state.attitude      = state.attitude      + (dt / 6) * (ad1 + 2*ad2 + 2*ad3 + ad4)
    new_state.angular_rates = state.angular_rates + (dt / 6) * (od1 + 2*od2 + 2*od3 + od4)
    new_state.fuel_mass     = max(state.fuel_mass - (dt / 6) * (fd1 + 2*fd2 + 2*fd3 + fd4) * dt, 0.0)
    new_state.engine_state  = (eng1 + 2*eng2 + 2*eng3 + eng4) / 6
    new_state.time          = state.time + dt

    return new_state


# =============================================================================
# SECTION 7 — SENSOR & AVIONICS LAYER
# =============================================================================

@dataclass
class SensorReadings:
    # GNSS
    gnss_position:    np.ndarray  = field(default_factory=lambda: np.zeros(3))
    gnss_signal:      float       = 95.0    # signal strength 0-100
    gnss_valid:       bool        = True

    # INS (drifts over time without GNSS correction)
    ins_position:     np.ndarray  = field(default_factory=lambda: np.zeros(3))
    ins_drift:        float       = 0.0     # accumulated drift (m)

    # Fused (Kalman)
    fused_position:   np.ndarray  = field(default_factory=lambda: np.zeros(3))

    # Airspeed (pitot tube)
    airspeed_mps:     float       = 0.0

    # Altimeter
    altitude_baro_m:  float       = 0.0

    # IMU
    accel_body:       np.ndarray  = field(default_factory=lambda: np.zeros(3))
    gyro_body:        np.ndarray  = field(default_factory=lambda: np.zeros(3))

    # Derived
    mach:             float       = 0.0
    alpha_deg:        float       = 0.0


class SensorLayer:
    """
    Simulates all onboard sensors with realistic noise, delay, and
    GNSS jamming degradation.
    """

    def __init__(self, params: AircraftParams, seed: int = 42):
        self.rng          = np.random.default_rng(seed)
        self.ins_pos      = None       # INS last known position
        self.ins_drift_m  = 0.0
        self.gnss_signal  = 95.0
        self.jamming      = False
        self.jamming_step = 0

        # Simple Kalman filter state
        self.kalman_pos   = None
        self.kalman_P     = np.eye(3) * 100.0   # error covariance

    def introduce_jamming(self, intensity: float = 4.0):
        """Call this to begin GNSS degradation event."""
        self.jamming           = True
        self.jamming_intensity = intensity

    def stop_jamming(self):
        self.jamming = False

    def _update_gnss_signal(self, dt: float) -> float:
        if self.jamming:
            self.jamming_step += 1
            if self.jamming_step < 10:
                drop = self.rng.uniform(0.5, 1.8) * self.jamming_intensity * 0.5
            else:
                drop = self.rng.uniform(2.5, 4.5) * self.jamming_intensity * 0.25
            self.gnss_signal = max(self.gnss_signal - drop, 12.0)
        else:
            # Gradual recovery when jamming stops
            self.gnss_signal = min(self.gnss_signal + self.rng.uniform(0.2, 0.8), 95.0)
            self.jamming_step = 0
        return self.gnss_signal

    def _gnss_noise(self, true_pos: np.ndarray, signal: float) -> np.ndarray:
        """
        GNSS position noise increases as signal degrades.
        At signal=95: ~3m noise. At signal=20: ~50m noise.
        """
        noise_scale = 3.0 + (95.0 - signal) * 0.6
        return true_pos + self.rng.normal(0, noise_scale, 3)

    def _ins_update(self, true_pos: np.ndarray, dt: float) -> np.ndarray:
        """
        INS dead reckoning with drift accumulation.
        Typical INS drift: ~0.8 nm/hr = ~1.5 m/min.
        """
        drift_rate = 0.025   # m/s
        self.ins_drift_m += drift_rate * dt
        drift_vec = self.rng.normal(0, self.ins_drift_m * 0.1, 3)
        if self.ins_pos is None:
            self.ins_pos = true_pos.copy()
        self.ins_pos = true_pos + drift_vec
        return self.ins_pos

    def _kalman_fuse(self, gnss: np.ndarray, ins: np.ndarray,
                     signal: float) -> np.ndarray:
        """
        Simple 1D Kalman filter fusing GNSS and INS.
        GNSS measurement noise increases with signal degradation.
        INS process noise increases with accumulated drift.
        """
        if self.kalman_pos is None:
            self.kalman_pos = gnss.copy()

        # Predict (use INS as process model)
        x_pred = ins
        P_pred = self.kalman_P + np.eye(3) * (self.ins_drift_m * 0.01)

        # Update (GNSS measurement)
        R_noise = np.eye(3) * max((95.0 - signal) * 2.0, 5.0)
        K = P_pred @ np.linalg.inv(P_pred + R_noise)
        self.kalman_pos = x_pred + K @ (gnss - x_pred)
        self.kalman_P  = (np.eye(3) - K) @ P_pred

        return self.kalman_pos

    def read(self, state: AircraftState, params: AircraftParams,
             dt: float) -> SensorReadings:
        """
        Reads all sensors for current aircraft state.
        Returns SensorReadings with noise applied.
        """
        alt   = -state.position[2]
        V     = np.linalg.norm(state.velocity_body)
        a     = speed_of_sound(alt)
        mach  = V / max(a, 1.0)
        u, v, w = state.velocity_body
        alpha = np.degrees(np.arctan2(w, max(u, 0.1)))

        # GNSS
        signal    = self._update_gnss_signal(dt)
        gnss_pos  = self._gnss_noise(state.position, signal)
        gnss_ok   = signal > 20.0

        # INS
        ins_pos   = self._ins_update(state.position, dt)

        # Kalman fusion
        fused     = self._kalman_fuse(gnss_pos, ins_pos, signal)

        # Pitot tube (airspeed) — Gaussian noise ~0.5 m/s
        _, _, rho = isa_atmosphere(alt)
        airspeed  = V + self.rng.normal(0, 0.5)

        # Barometric altimeter — noise ~5 m
        alt_baro  = alt + self.rng.normal(0, 5.0)

        # IMU — gyro noise ~0.01 rad/s, accel noise ~0.05 m/s²
        gyro  = state.angular_rates + self.rng.normal(0, 0.01,  3)
        accel = np.array([
            (np.linalg.norm(state.velocity_body) - V) / max(dt, 1e-6),
            0.0, 0.0
        ]) + self.rng.normal(0, 0.05, 3)

        return SensorReadings(
            gnss_position   = gnss_pos,
            gnss_signal     = round(signal, 2),
            gnss_valid      = gnss_ok,
            ins_position    = ins_pos,
            ins_drift       = self.ins_drift_m,
            fused_position  = fused,
            airspeed_mps    = max(airspeed, 0.0),
            altitude_baro_m = max(alt_baro, 0.0),
            accel_body      = accel,
            gyro_body       = gyro,
            mach            = mach,
            alpha_deg       = alpha,
        )


# =============================================================================
# SECTION 8 — DIGITAL TWIN CLASS
# Wraps physics model + sensors into single interface
# =============================================================================

class DigitalTwin:
    """
    The I.R.I.S. Digital Twin.
    Combines 6-DOF flight dynamics, RK4 integration, and full sensor layer
    into the base world model for QDRL-AP.

    Usage:
        twin = DigitalTwin()
        sensors = twin.step(controls, dt)
        state   = twin.state
    """

    def __init__(self, dt: float = 0.02, seed: int = 42):
        self.params  = AircraftParams()
        self.state   = AircraftState()
        self.sensors = SensorLayer(self.params, seed=seed)
        self.dt      = dt
        self.history = []

    def step(self, controls: ControlInputs) -> SensorReadings:
        """
        Advance simulation by one timestep.
        Integrates EOM, reads sensors, logs state.
        Returns current SensorReadings.
        """
        self.state = rk4_step(self.state, controls, self.params, self.dt)
        readings   = self.sensors.read(self.state, self.params, self.dt)
        self._log(readings)
        return readings

    def introduce_jamming(self, intensity: float = 4.0):
        self.sensors.introduce_jamming(intensity)

    def stop_jamming(self):
        self.sensors.stop_jamming()

    def _log(self, readings: SensorReadings):
        alt = -self.state.position[2]
        V   = np.linalg.norm(self.state.velocity_body)
        self.history.append({
            'time':         round(self.state.time, 3),
            'altitude_m':   round(alt, 1),
            'airspeed_mps': round(V, 2),
            'mach':         round(readings.mach, 4),
            'alpha_deg':    round(readings.alpha_deg, 2),
            'roll_deg':     round(np.degrees(self.state.attitude[0]), 2),
            'pitch_deg':    round(np.degrees(self.state.attitude[1]), 2),
            'fuel_kg':      round(self.state.fuel_mass, 1),
            'gnss_signal':  readings.gnss_signal,
            'gnss_valid':   readings.gnss_valid,
            'ins_drift_m':  round(readings.ins_drift, 2),
        })

    def proximity_variables(self, readings: SensorReadings) -> Dict:
        """
        Returns the set of continuous proximity variables monitored
        by π₁ and π₂ for near-breach detection.
        """
        alt = -self.state.position[2]
        V   = np.linalg.norm(self.state.velocity_body)
        a   = speed_of_sound(alt)

        return {
            # Communication
            'gnss_signal':      readings.gnss_signal,
            'gnss_valid':       readings.gnss_valid,
            # Speed envelope
            'mach':             readings.mach,
            'mach_limit':       0.82,
            # Altitude
            'altitude_m':       alt,
            'altitude_min_m':   300.0,
            # Stall margin
            'alpha_deg':        readings.alpha_deg,
            'alpha_stall_deg':  np.degrees(self.params.alpha_stall),
            # Fuel
            'fuel_kg':          self.state.fuel_mass,
            'fuel_min_kg':      1500.0,
            # INS drift (backup nav quality)
            'ins_drift_m':      readings.ins_drift,
        }

    def print_state(self, readings: SensorReadings):
        pv = self.proximity_variables(readings)
        print(f"  t={self.state.time:6.1f}s | "
              f"Alt:{pv['altitude_m']:7.0f}m | "
              f"Mach:{pv['mach']:.3f} | "
              f"α:{pv['alpha_deg']:5.1f}° | "
              f"Fuel:{pv['fuel_kg']:6.0f}kg | "
              f"GNSS:{pv['gnss_signal']:5.1f} | "
              f"INS drift:{pv['ins_drift_m']:5.1f}m")


# =============================================================================
# QUICK SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 65)
    print("  I.R.I.S. Digital Twin — Self Test")
    print("=" * 65)

    twin     = DigitalTwin(dt=0.02)
    controls = ControlInputs(throttle=0.75, elevator=0.01)

    print("\n  Running 5 seconds of normal flight (250 Hz equiv via RK4)...")
    for i in range(250):
        readings = twin.step(controls)

    twin.print_state(readings)

    print("\n  Introducing GNSS jamming...")
    twin.introduce_jamming(intensity=3.5)

    for i in range(250):
        readings = twin.step(controls)

    twin.print_state(readings)
    print(f"\n  GNSS signal: {readings.gnss_signal:.1f} | Valid: {readings.gnss_valid}")
    print(f"  INS drift accumulated: {readings.ins_drift:.2f} m")
    print("\n  Digital twin self-test complete.")
    print("=" * 65)
