"""
CIRS v1.0: Coherence-Integrity Resonance System
Fully integrated with UNITARES Phase-Aware Dynamics.

Implements oscillation detection and resonance damping, adjusting aggressiveness
based on the agent's phase (Exploration = forgiving, Integration = strict).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import math

# We will interface with the Phase-aware metrics so damping adapts
from .phase_aware import Phase


@dataclass
class OscillationState:
    """State tracked by OscillationDetector."""
    oi: float = 0.0                    # Current Oscillation Index
    flips: int = 0                     # Flip count in window
    resonant: bool = False             # Whether resonance detected
    trigger: Optional[str] = None      # 'oi' or 'flips' or None
    ema_coherence: float = 0.0         # EMA of coherence transitions
    ema_risk: float = 0.0              # EMA of risk transitions


class OscillationDetector:
    """
    Detect oscillatory patterns in governance decisions.
    Implements CIRS v1.0 Oscillation Index with phase awareness.

    OI_t = EMA_λ(sign(Δcoherence_t) - sign(Δcoherence_{t-1})) +
           EMA_λ(sign(Δrisk_t) - sign(Δrisk_{t-1}))
    """

    def __init__(self,
                 window: int = 10,
                 ema_lambda: float = 0.35,
                 oi_threshold: float = 2.5,
                 flip_threshold: int = 4):
        self.window = window
        self.ema_lambda = ema_lambda
        # Default thresholds (Integration mode typical)
        self.base_oi_threshold = oi_threshold
        self.base_flip_threshold = flip_threshold
        
        self.history: List[Dict] = []
        self.ema_coherence = 0.0
        self.ema_risk = 0.0

    def get_phase_thresholds(self, phase: str) -> Tuple[float, int]:
        """Adjust thresholds based on operating phase."""
        if phase == Phase.EXPLORATION:
            # During exploration, more oscillation is normal and acceptable.
            # We increase the thresholds so we don't damp learning artificially.
            return self.base_oi_threshold * 1.5, self.base_flip_threshold + 2
        else:
            # Integration phase: expect stability. Tighten thresholds.
            return self.base_oi_threshold, self.base_flip_threshold

    def update(self, coherence: float, risk: float,
               route: str, threshold_coherence: float,
               threshold_risk: float, phase: str = Phase.INTEGRATION) -> OscillationState:
        
        delta_coh = coherence - threshold_coherence
        delta_risk = risk - threshold_risk

        self.history.append({
            'route': route,
            'sign_coh': 1 if delta_coh >= 0 else -1,
            'sign_risk': 1 if delta_risk >= 0 else -1
        })

        if len(self.history) > self.window:
            self.history.pop(0)

        oi = self._compute_oi()
        flips = self._count_flips()

        resonant = False
        trigger = None

        oi_threshold, flip_threshold = self.get_phase_thresholds(phase)

        if abs(oi) >= oi_threshold:
            resonant = True
            trigger = 'oi'
        elif flips >= flip_threshold:
            resonant = True
            trigger = 'flips'

        return OscillationState(
            oi=oi,
            flips=flips,
            resonant=resonant,
            trigger=trigger,
            ema_coherence=self.ema_coherence,
            ema_risk=self.ema_risk
        )

    def _compute_oi(self) -> float:
        if len(self.history) < 2:
            return 0.0

        # Only process the LATEST transition incrementally (not the full history).
        # The EMA accumulators persist across calls, so reprocessing old
        # transitions would compound values incorrectly.
        coh_transition = self.history[-1]['sign_coh'] - self.history[-2]['sign_coh']
        risk_transition = self.history[-1]['sign_risk'] - self.history[-2]['sign_risk']

        self.ema_coherence = self.ema_lambda * coh_transition + (1 - self.ema_lambda) * self.ema_coherence
        self.ema_risk = self.ema_lambda * risk_transition + (1 - self.ema_lambda) * self.ema_risk

        return self.ema_coherence + self.ema_risk

    def _count_flips(self) -> int:
        if len(self.history) < 2:
            return 0
        flips = sum(1 for i in range(1, len(self.history)) if self.history[i]['route'] != self.history[i-1]['route'])
        return flips


@dataclass
class DampingResult:
    tau_new: float
    beta_new: float
    damping_applied: bool
    adjustments: Dict = field(default_factory=dict)


class ResonanceDamper:
    """
    Apply damping when oscillation/resonance detected.
    Implements CIRS v1.0.
    
    Adjusts kappa_r (damping rate) based on Phase.
    """
    def __init__(self,
                 base_kappa_r: float = 0.15,
                 delta_tau: float = 0.08,
                 tau_bounds: Tuple[float, float] = (0.25, 0.75),
                 beta_bounds: Tuple[float, float] = (0.2, 0.6)):
        self.base_kappa_r = base_kappa_r
        self.delta_tau = delta_tau
        self.tau_bounds = tau_bounds
        self.beta_bounds = beta_bounds

    def apply_damping(self,
                      current_coherence: float,
                      current_risk: float,
                      tau: float,
                      beta: float,
                      oscillation_state: OscillationState,
                      phase: str = Phase.INTEGRATION) -> DampingResult:
        if not oscillation_state.resonant:
            return DampingResult(tau, beta, False, {})

        # Exploration phase -> gentler damping; Integration -> stricter damping
        kappa_r = self.base_kappa_r * 0.5 if phase == Phase.EXPLORATION else self.base_kappa_r

        delta_coh = tau - current_coherence
        delta_risk = beta - current_risk

        d_tau = max(-self.delta_tau, min(self.delta_tau, delta_coh))
        d_beta = max(-self.delta_tau, min(self.delta_tau, delta_risk))

        tau_new = tau + kappa_r * (-d_tau)
        beta_new = beta + kappa_r * (-d_beta)

        tau_new = max(self.tau_bounds[0], min(self.tau_bounds[1], tau_new))
        beta_new = max(self.beta_bounds[0], min(self.beta_bounds[1], beta_new))

        return DampingResult(
            tau_new=tau_new,
            beta_new=beta_new,
            damping_applied=True,
            adjustments={
                'd_tau': tau_new - tau,
                'd_beta': beta_new - beta,
                'trigger': oscillation_state.trigger,
                'kappa_applied': kappa_r,
                'phase': phase
            }
        )
