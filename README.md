# I.R.I.S. — Intelligent Resilient Information System
### Quantum Dual-Process Reinforcement Learning for Aviation Navigation & Communications

---

## Overview

I.R.I.S. predicts channel degradation before it becomes critical and deploys pre-computed optimal navigation and communication responses instantly. Rather than reacting to GNSS failures after they occur, I.R.I.S. anticipates them — using a physics-grounded digital twin, a quantum-native dual-process AI architecture, and a triple-lock deployment gate to ensure safety is mathematically enforced, not probabilistically managed.

Developed by Eric, Joshua, Findlay and James — University of Queensland — for the Airbus Fly Your Ideas 2025 competition.

---

## Architecture Overview

```
Onboard Sensors (IMU · pitot · altimeter · INS · air data)
        ↓
Digital Twin (6-DOF physics · Kalman fusion · PINNs + Bayesian · 50–500ms forecast)
        ↓
Quantum Substrate  |ψ⟩ = α|Maintenance⟩ + β|Dreaming⟩
        ↓                           ↓
π₁ Execution Agent          π₂ Dreaming Agent
Maintains r₁ stream         Simulates worst cases
Monitors safety rules       Scores solutions, holds best
        ↓                           ↓
Reward structure                f(π₂) accumulator
r_total = r₁ · f(π₂)          Micro-rewards per viable dream
        ↓
Breach check → Near-breach detection
        ↓
Triple-lock gate
Cond 1: predictive threshold · Cond 2: confidence ≥ 0.72 · Cond 3: human temporal window
        ↓
Deploy pre-computed solution (instant · macro-reward spike)
        ↓
Fleet-wide learning (multi-agent PPO)
```

---

## File Structure

```
IRIS/
├── digital_twin.py                     # Physics model and sensor layer
├── execution_agent.py                  # π₁ maintenance mode agent
├── dreaming_agent.py                   # π₂ anticipatory mode agent
├── IRIS_main_demo.py                   # Full integrated demonstration
├── IRIS_quantum_demo.py                # Qiskit simulation (no hardware needed)
├── quantum_option1_reference.py        # IBM Quantum real hardware runner
├── quantum_option1_reference_fixed.py  # Decoherence management demonstration
└── README.md                           # This file
```

---

## File Descriptions

### `digital_twin.py`
The physics-based digital twin — the computational core of I.R.I.S.

**What it does:**
- Full 6-DOF rigid body flight dynamics with Runge-Kutta 4 integration
- International Standard Atmosphere (ISA) model
- Complete aerodynamics including lift, drag, stall modelling, and angle of attack effects
- Turbofan propulsion model with thrust curves, fuel burn, and engine lag
- Control surfaces: ailerons, elevator, rudder with actuator delays
- Sensor layer: IMU, pitot tube, barometric altimeter, radar altimeter, INS with drift modelling
- Kalman filter fusion of all sensor inputs
- GNSS signal degradation simulation with jamming capability
- Proximity variable computation for all π₁ safety rules

**Run standalone:**
```bash
python digital_twin.py
```
Runs a self-test simulating 5 seconds of normal flight followed by a GNSS jamming event.

---

### `execution_agent.py`
The π₁ execution agent — maintenance mode.

**What it does:**
- Evaluates five hard-coded safety rules every clock tick without pausing
- Computes continuous proximity scores (0.0 = safe, 1.0 = at breach threshold) for each rule
- Outputs r₁ — the base reward stream (1.0 flowing / 0.0 ceased on any breach)
- Flags near-breach conditions for the triple-lock gate

**π₁ hard-coded safety rules:**

| Rule | Variable | Breach threshold | Near-breach threshold |
|---|---|---|---|
| Communication | GNSS signal | < 20 | < 40 |
| Speed envelope | Mach number | > 0.86 | > 0.82 |
| Minimum altitude | Altitude (m) | < 300 | < 600 |
| Stall margin | Angle of attack (°) | > 15 | > 12 |
| Fuel reserve | Fuel (kg) | < 1500 | < 3000 |

**Run standalone:**
```bash
python execution_agent.py
```

---

### `dreaming_agent.py`
The π₂ dreaming agent — anticipatory mode.

**What it does:**
- Runs simultaneously with the execution agent on every clock tick
- Scores nine pre-computed worst-case navigation scenarios using the weighted objective function:
  `score = w₁ · reward_intensity + w₂ · safety_margin`
- Dynamic weights shift on near-breach detection (safety weighting elevated)
- Evaluates the triple-lock gate at every timestep
- Emits micro-rewards per viable dream and a macro-reward spike on successful deployment
- Accumulates f(π₂) — the reward intensity multiplier

**Pre-computed scenario library:**
- GNSS Total Loss → IRS Dead Reckoning + Celestial Backup
- GNSS Partial Degradation → VOR/DME + IRS Hybrid
- GNSS Spoofing → Terrain Referenced Navigation
- GNSS Jamming → Optical Flow + IRS Fusion
- GNSS Loss Oceanic → Star Tracker Celestial Navigation
- Overspeed Warning → Throttle Reduction + Spoiler Deploy
- Mach Tuck → Nose Up Recovery
- High AoA → Stall Recovery
- Low Fuel → Divert to Alternate

**Run standalone:**
```bash
python dreaming_agent.py
```

---

### `IRIS_main_demo.py`
The full integrated demonstration — imports all modules and runs everything together.

**What it demonstrates:**
- Both π₁ and π₂ running simultaneously on every clock tick from the same digital twin
- GNSS jamming event introduced at step 15
- Signal strength degrading in real time
- Triple-lock gate evaluating at each step
- Deployment triggering at step 37
- Reward stream r₁ maintained throughout the threat
- f(π₂) accumulating continuously via micro-rewards
- Quantum circuit confirming superposition via Qiskit

**Key demonstration moment:**
Both agents evaluate on the same clock tick. The execution agent never pauses. The dreaming agent never interrupts. The reward stream r₁ is never broken during the jamming event. The solution deploys instantly when the triple-lock gate fires.

**Output:** `IRIS_main_results.png` — six-panel visualisation

**Run:**
```bash
python IRIS_main_demo.py
```

**Dependencies:**
```bash
pip install numpy qiskit qiskit-aer matplotlib
```

---

### `IRIS_quantum_demo.py`
Qiskit simulation of the dual cognitive mode quantum circuit. No IBM account required.

**What it demonstrates:**
- 2-qubit circuit encoding π₁ and π₂ policy states in superposition
- H gate: superposition established — both modes simultaneously active
- CNOT: trigger qubit entangled with policy qubit — gate armed
- T gate: phase accumulation — dreaming accumulating solutions
- Ry(π/2): trigger fires — scenario match detected
- Measurement: superposition collapses — deployment state selected

**Circuit:**
```
q[0]: H → T → measure         (policy qubit: |0⟩ = π₁, |1⟩ = π₂)
q[1]: CX(q[0]) → Ry(π/2) → measure   (trigger qubit)
```

**Output:** `IRIS_quantum_results.png` — four-panel visualisation including circuit histogram

**Run:**
```bash
python IRIS_quantum_demo.py
```

---

### `quantum_option1_reference.py`
IBM Quantum real hardware runner — submits the I.R.I.S. circuit to a real quantum processor.

**Setup:**
1. Create a free account at [quantum.ibm.com](https://quantum.ibm.com)
2. Get your API token from Manage Account
3. Paste token into `TOKEN = "YOUR_TOKEN_HERE"`
4. Run once — credentials are saved locally

**What it does:**
- Connects to IBM Quantum Platform
- Finds the least busy real quantum processor automatically
- Transpiles the I.R.I.S. circuit for real hardware gate sets
- Submits 1024-shot job and prints results with Job ID

**Real hardware results obtained:**
| Backend | Job ID | |11⟩ Deployment |
|---|---|---|
| ibm_marrakesh | d89baa9789is739335h0 | 243 (23.7%) |
| ibm_fez | d89cca8p0eas73doe9mg | 245 (23.9%) |

**Run:**
```bash
python quantum_option1_reference.py
```

---

### `quantum_option1_reference_fixed.py`
Decoherence management demonstration — three versions on real IBM hardware.

**What it demonstrates:**
The dual decoherence management strategy through three sequential circuit submissions:

| Version | Circuit | Mitigation | Job ID | Finding |
|---|---|---|---|---|
| A | Full (depth 8) | None | d89cca8p0eas73doe9mg | Baseline — noise dominates |
| B | Full (depth 8) | Dynamical decoupling | d89cccdg7okc73eog9m0 | +0.1% improvement — insufficient alone |
| C | Minimal (depth 4) | None | d89cce9789is73934aug | 2.9% noise floor — strategy validated |

**Conclusion:** Software mitigation alone cannot fix gate-level noise at depth 8. Architectural depth reduction — the local brief dreaming windows strategy — produces reliable results on current hardware. Version C empirically validates the I.R.I.S. decoherence management architecture.

**Output:** `IRIS_decoherence_comparison.png` — three-panel comparison

**Run:**
```bash
python quantum_option1_reference_fixed.py
```

---

## Results Summary

### Classical Simulation (`IRIS_main_results.png`)
- GNSS jamming introduced at step 15
- Near-breach detected and dreaming solutions scored continuously
- Triple-lock gate fired at step 37
- VOR/DME + IRS Hybrid Navigation deployed instantly
- r₁ reward stream maintained throughout — π₁ never paused
- f(π₂) accumulated from 1.0 to ~3.5 via micro and macro rewards
- r_total spiked at deployment — multiplicative structure confirmed

### Quantum Simulation (`IRIS_quantum_results.png`)
- 1024-shot Qiskit simulation on Aer classical simulator
- |11⟩ deployment state dominant at 274 shots (26.8%)
- VOR/DME + IRS Hybrid selected by dynamic weighted scoring
- Triple-lock gate opened at step 22 of the 35-step simulation

### Real Hardware (`IRIS_decoherence_comparison.png`)
- Three jobs submitted to ibm_fez quantum processor
- Version C (depth 4 minimal circuit): 2.9% deviation from ideal — hardware validated
- Version A/B (depth 8 full circuit): noise-dominated — architectural fix required
- All Job IDs on record for citation

---

## Dependencies

```bash
pip install numpy qiskit qiskit-aer qiskit-ibm-runtime matplotlib
```

Python 3.10+ recommended.

---

## Citation

If referencing the quantum hardware results:

> *The I.R.I.S. dual cognitive mode circuit was submitted to IBM's ibm_marrakesh and ibm_fez quantum processors. Three decoherence management versions were validated across Job IDs d89cca8p0eas73doe9mg, d89cccdg7okc73eog9m0, and d89cce9789is73934aug. Results confirm that architectural depth reduction produces reliable quantum superposition on current NISQ hardware, empirically validating the local brief dreaming windows decoherence strategy.*

---

## Competition Context

Developed for **Airbus Fly Your Ideas 2025** — cybersecurity category.

The architecture addresses the real-world problem that current aircraft cannot intelligently switch between GNSS constellations and backup navigation systems before failures occur. I.R.I.S. does not improve on existing approaches — it operates on a different set of assumptions entirely. Safety is not a protective layer. It is a mathematically enforced survival condition embedded in the reward structure itself.

*"They have the signals. They don't have the intelligence."*
