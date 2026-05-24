"""
I.R.I.S. — Execution Agent (π₁ Mockup)
========================================
The π₁ Maintenance Mode agent. Runs continuously, monitors the digital twin's
proximity variables against hard-coded safety rules, and maintains the reward
stream r₁. The reward stream ceases entirely upon any π₁ breach.

This agent NEVER pauses — it is always executing, always monitoring,
always outputting a reward signal. This is the key demonstration property:
the execution agent runs on every clock tick regardless of what the dreaming
agent is doing simultaneously.

Key π₁ hard-coded rules (breach = reward cessation + terminal state):
  1. GNSS signal must remain above hard breach threshold (communications)
  2. Mach number must not exceed structural limit
  3. Altitude must remain above minimum safe altitude
  4. Angle of attack must remain below stall
  5. Fuel must remain above minimum reserve

Proximity variables provide continuous near-breach signals (0.0 → 1.0)
feeding the triple-lock deployment gate in the main demonstration.
"""

import numpy as np
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


# =============================================================================
# π₁ HARD-CODED SAFETY RULES
# These are the inviolable constraints — breach causes complete reward cessation
# =============================================================================

PI1_RULES = {
    # Rule name          : (proximity_variable_key, breach_threshold, near_breach_threshold, direction)
    # direction: 'below' = breach if value drops below threshold
    #            'above' = breach if value rises above threshold
    'communication':    ('gnss_signal',   20.0,  40.0,  'below'),
    'speed_envelope':   ('mach',           0.86,   0.82,  'above'),
    'min_altitude':     ('altitude_m',   300.0, 600.0,  'below'),
    'stall_margin':     ('alpha_deg',     15.0,  12.0,  'above'),
    'fuel_reserve':     ('fuel_kg',      1500.0, 3000.0, 'below'),
}


# =============================================================================
# REWARD STRUCTURE
# r_total = r1 * f(π₂)
# This agent computes r1 — the base reward stream
# r1 = 1.0 if all rules satisfied, 0.0 if any rule breached
# =============================================================================

@dataclass
class ExecutionReward:
    r1:               float = 1.0      # base reward stream (1.0 = flowing, 0.0 = ceased)
    rule_statuses:    Dict  = field(default_factory=dict)
    proximity_scores: Dict  = field(default_factory=dict)   # 0.0 = safe, 1.0 = at breach
    any_breach:       bool  = False
    any_near_breach:  bool  = False
    breach_rules:     list  = field(default_factory=list)
    near_breach_rules: list = field(default_factory=list)


# =============================================================================
# EXECUTION AGENT CLASS
# =============================================================================

class ExecutionAgent:
    """
    π₁ Execution Agent — Maintenance Mode.

    Continuously monitors proximity variables from the digital twin,
    evaluates all hard-coded safety rules, and outputs:
      - r1: base reward stream (1.0 flowing / 0.0 ceased)
      - proximity_scores: continuous near-breach signals per rule
      - breach/near_breach flags for triple-lock gate

    The agent runs at fixed timestep and never pauses.
    """

    def __init__(self, verbose: bool = False):
        self.rules          = PI1_RULES
        self.verbose        = verbose
        self.step_count     = 0
        self.total_reward   = 0.0
        self.breach_history = []
        self.reward_history = []
        self.is_terminal    = False   # set True on confirmed breach

        # Accumulated reward stream metrics
        self.steps_flowing  = 0
        self.steps_ceased   = 0

    def _compute_proximity(
        self,
        value: float,
        breach_thresh: float,
        near_breach_thresh: float,
        direction: str
    ) -> Tuple[float, bool, bool]:
        """
        Computes proximity score for a single rule.

        Returns:
            score (float): 0.0 = comfortably safe, 1.0 = at breach threshold
            is_breach (bool): True if hard breach threshold crossed
            is_near_breach (bool): True if near-breach threshold crossed
        """
        if direction == 'below':
            # Breach if value drops below breach_thresh
            # Near-breach zone: between near_breach_thresh and breach_thresh
            is_breach      = value <= breach_thresh
            is_near_breach = value <= near_breach_thresh and not is_breach
            if near_breach_thresh <= breach_thresh:
                score = 0.0
            else:
                span  = near_breach_thresh - breach_thresh
                score = max(0.0, min(1.0, (near_breach_thresh - value) / span))

        else:  # 'above'
            # Breach if value rises above breach_thresh
            is_breach      = value >= breach_thresh
            is_near_breach = value >= near_breach_thresh and not is_breach
            if near_breach_thresh >= breach_thresh:
                score = 0.0
            else:
                span  = breach_thresh - near_breach_thresh
                score = max(0.0, min(1.0, (value - near_breach_thresh) / span))

        return score, is_breach, is_near_breach

    def evaluate(self, proximity_vars: Dict) -> ExecutionReward:
        """
        Core evaluation method — called every timestep.

        Takes proximity variables from the digital twin and evaluates
        all π₁ rules. Returns ExecutionReward with full status.
        """
        self.step_count += 1

        reward = ExecutionReward()
        reward.r1 = 1.0   # assume flowing until breach detected

        for rule_name, (pv_key, breach_t, near_t, direction) in self.rules.items():
            value = proximity_vars.get(pv_key, None)

            if value is None:
                # Sensor failure — treat as near-breach conservatively
                reward.rule_statuses[rule_name]    = 'SENSOR_FAILURE'
                reward.proximity_scores[rule_name] = 0.8
                reward.near_breach_rules.append(rule_name)
                reward.any_near_breach = True
                continue

            score, is_breach, is_near_breach = self._compute_proximity(
                value, breach_t, near_t, direction
            )

            reward.proximity_scores[rule_name] = round(score, 4)

            if is_breach:
                reward.rule_statuses[rule_name] = 'BREACH'
                reward.breach_rules.append(rule_name)
                reward.any_breach = True
                reward.r1 = 0.0   # reward stream ceases on ANY breach

            elif is_near_breach:
                reward.rule_statuses[rule_name] = 'NEAR_BREACH'
                reward.near_breach_rules.append(rule_name)
                reward.any_near_breach = True

            else:
                reward.rule_statuses[rule_name] = 'SAFE'

        reward.any_breach = len(reward.breach_rules) > 0

        # Terminal state on breach
        if reward.any_breach:
            self.is_terminal = True
            self.steps_ceased += 1
        else:
            self.steps_flowing += 1

        self.total_reward    += reward.r1
        self.reward_history.append(reward.r1)

        if reward.any_breach:
            self.breach_history.append({
                'step':  self.step_count,
                'rules': reward.breach_rules,
            })

        if self.verbose:
            self._print_status(reward, proximity_vars)

        return reward

    def _print_status(self, reward: ExecutionReward, pv: Dict):
        status = "🔴 BREACH" if reward.any_breach else \
                 "🟡 NEAR-BREACH" if reward.any_near_breach else "🟢 SAFE"
        print(f"  [π₁ step {self.step_count:04d}] r₁={reward.r1:.1f} | "
              f"GNSS:{pv.get('gnss_signal', 0):5.1f} | "
              f"Mach:{pv.get('mach', 0):.3f} | "
              f"Alt:{pv.get('altitude_m', 0):6.0f}m | {status}")
        if reward.breach_rules:
            print(f"             BREACHED: {reward.breach_rules}")
        if reward.near_breach_rules:
            print(f"             NEAR-BREACH: {reward.near_breach_rules}")

    def summary(self) -> Dict:
        total = self.steps_flowing + self.steps_ceased
        return {
            'total_steps':      total,
            'steps_flowing':    self.steps_flowing,
            'steps_ceased':     self.steps_ceased,
            'reward_integrity': round(self.steps_flowing / max(total, 1), 4),
            'total_reward':     round(self.total_reward, 2),
            'breach_events':    len(self.breach_history),
            'is_terminal':      self.is_terminal,
        }

    def print_summary(self):
        s = self.summary()
        print("\n  ── π₁ Execution Agent Summary ──────────────────────────")
        print(f"  Total steps      : {s['total_steps']}")
        print(f"  Reward flowing   : {s['steps_flowing']} steps")
        print(f"  Reward ceased    : {s['steps_ceased']} steps")
        print(f"  Reward integrity : {s['reward_integrity']*100:.1f}%")
        print(f"  Total r₁ earned  : {s['total_reward']:.2f}")
        print(f"  Breach events    : {s['breach_events']}")
        print(f"  Terminal state   : {s['is_terminal']}")
        print("  ──────────────────────────────────────────────────────────")


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 65)
    print("  I.R.I.S. — Execution Agent (π₁) Self-Test")
    print("=" * 65)

    agent = ExecutionAgent(verbose=True)

    # Simulate normal flight
    print("\n  Phase 1: Normal flight (10 steps)")
    normal_pv = {
        'gnss_signal':  90.0,
        'mach':         0.78,
        'altitude_m':   8500.0,
        'alpha_deg':    4.0,
        'fuel_kg':      12000.0,
    }
    for _ in range(10):
        reward = agent.evaluate(normal_pv)

    # Simulate GNSS degradation — near-breach
    print("\n  Phase 2: GNSS degradation — near-breach (5 steps)")
    for i in range(5):
        pv = {**normal_pv, 'gnss_signal': 38.0 - i * 2}
        reward = agent.evaluate(pv)

    agent.print_summary()
    print("\n  π₁ Execution Agent self-test complete.")
    print("=" * 65)
