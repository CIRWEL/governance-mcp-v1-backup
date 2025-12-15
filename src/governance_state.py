"""
Governance State Module

Wrapper around UNITARES Phase-3 State with additional tracking and history.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List

from governance_core import (
    State, Theta,
    DEFAULT_STATE, DEFAULT_THETA,
    lambda1 as lambda1_from_theta,
    DynamicsParams, DEFAULT_PARAMS
)


@dataclass
class GovernanceState:
    """Wrapper around UNITARES Phase-3 State with additional tracking"""
    
    # UNITARES Phase-3 state (internal engine)
    unitaires_state: State = field(default_factory=lambda: State(
        E=DEFAULT_STATE.E,
        I=DEFAULT_STATE.I,
        S=DEFAULT_STATE.S,
        V=DEFAULT_STATE.V
    ))
    unitaires_theta: Theta = field(default_factory=lambda: Theta(
        C1=DEFAULT_THETA.C1,
        eta1=DEFAULT_THETA.eta1
    ))
    
    # Derived metrics (computed from UNITARES state)
    coherence: float = 1.0      # Computed from UNITARES coherence function
    void_active: bool = False     # Whether in void state (|V| > threshold)
    
    # History tracking
    time: float = 0.0
    update_count: int = 0
    
    # Regime tracking (operational state detection)
    regime: str = "divergence"  # DIVERGENCE | TRANSITION | CONVERGENCE | STABLE
    regime_history: List[str] = field(default_factory=list)  # Track regime over time
    locked_persistence_count: int = 0  # Count consecutive steps at STABLE threshold
    
    # Rolling statistics for adaptive thresholds
    E_history: List[float] = field(default_factory=list)  # Energy history
    I_history: List[float] = field(default_factory=list)  # Information integrity history
    S_history: List[float] = field(default_factory=list)  # Entropy history
    V_history: List[float] = field(default_factory=list)  # Void integral history
    coherence_history: List[float] = field(default_factory=list)
    risk_history: List[float] = field(default_factory=list)
    decision_history: List[str] = field(default_factory=list)  # Track approve/reflect/reject decisions
    timestamp_history: List[str] = field(default_factory=list)  # Track timestamps for each update
    lambda1_history: List[float] = field(default_factory=list)  # Track lambda1 adaptation over time
    
    # PI controller state
    pi_integral: float = 0.0  # Integral term state for PI controller (anti-windup protected)
    
    # Compatibility: expose E, I, S, V as properties for backward compatibility
    @property
    def E(self) -> float:
        return self.unitaires_state.E
    
    @property
    def I(self) -> float:
        return self.unitaires_state.I
    
    @property
    def S(self) -> float:
        return self.unitaires_state.S
    
    @property
    def V(self) -> float:
        return self.unitaires_state.V
    
    @property
    def lambda1(self) -> float:
        """Get lambda1 from UNITARES theta using governance_core (adaptive via eta1)"""
        # Pass lambda1 bounds from config to enable adaptive control
        from config.governance_config import config
        return lambda1_from_theta(
            self.unitaires_theta, 
            DEFAULT_PARAMS,
            lambda1_min=config.LAMBDA1_MIN,
            lambda1_max=config.LAMBDA1_MAX
        )
    
    def to_dict(self) -> Dict:
        """Export state as dictionary"""
        return {
            'E': float(self.E),
            'I': float(self.I),
            'S': float(self.S),
            'V': float(self.V),
            'coherence': float(self.coherence),
            'lambda1': float(self.lambda1),
            'void_active': bool(self.void_active),
            'regime': str(self.regime),  # Include current regime
            'time': float(self.time),
            'update_count': int(self.update_count)
        }
    
    def to_dict_with_history(self, max_history: int = 100) -> Dict:
        """
        Export state with history for persistence.

        Args:
            max_history: Maximum number of history entries to keep (default: 100)
                         This prevents unbounded state file growth.
        """
        # SECURITY: Cap history arrays to prevent disk exhaustion
        # Keep only the most recent max_history entries
        def cap_history(history_list, max_len=max_history):
            """Return last max_len entries from history"""
            if len(history_list) <= max_len:
                return history_list
            return history_list[-max_len:]

        return {
            # Current state values
            'E': float(self.E),
            'I': float(self.I),
            'S': float(self.S),
            'V': float(self.V),
            'coherence': float(self.coherence),
            'lambda1': float(self.lambda1),
            'void_active': bool(self.void_active),
            'time': float(self.time),
            'update_count': int(self.update_count),
            # UNITARES internal state
            'unitaires_state': {
                'E': float(self.unitaires_state.E),
                'I': float(self.unitaires_state.I),
                'S': float(self.unitaires_state.S),
                'V': float(self.unitaires_state.V)
            },
            'unitaires_theta': {
                'C1': float(self.unitaires_theta.C1),
                'eta1': float(self.unitaires_theta.eta1)
            },
            # History arrays (capped to last max_history entries)
            'regime': str(self.regime),
            'regime_history': [str(r) for r in cap_history(self.regime_history)],
            'locked_persistence_count': int(self.locked_persistence_count),
            'E_history': [float(e) for e in cap_history(self.E_history)],
            'I_history': [float(i) for i in cap_history(self.I_history)],
            'S_history': [float(s) for s in cap_history(self.S_history)],
            'V_history': [float(v) for v in cap_history(self.V_history)],
            'coherence_history': [float(c) for c in cap_history(self.coherence_history)],
            'risk_history': [float(r) for r in cap_history(self.risk_history)],
            'lambda1_history': [float(l) for l in cap_history(getattr(self, 'lambda1_history', []))],  # Lambda1 adaptation history
            'decision_history': list(cap_history(self.decision_history)),
            'timestamp_history': list(cap_history(self.timestamp_history)),  # Timestamps for each update
            'pi_integral': float(getattr(self, 'pi_integral', 0.0))  # PI controller integral state
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'GovernanceState':
        """Create GovernanceState from dictionary (for loading persisted state)"""
        from governance_core import State, Theta
        
        # Create state with loaded values
        state = cls()
        
        # Load UNITARES internal state
        if 'unitaires_state' in data:
            us = data['unitaires_state']
            state.unitaires_state = State(
                E=float(us.get('E', DEFAULT_STATE.E)),
                I=float(us.get('I', DEFAULT_STATE.I)),
                S=float(us.get('S', DEFAULT_STATE.S)),
                V=float(us.get('V', DEFAULT_STATE.V))
            )
        else:
            # Fallback: use current state values
            state.unitaires_state = State(
                E=float(data.get('E', DEFAULT_STATE.E)),
                I=float(data.get('I', DEFAULT_STATE.I)),
                S=float(data.get('S', DEFAULT_STATE.S)),
                V=float(data.get('V', DEFAULT_STATE.V))
            )
        
        # Load UNITARES theta
        if 'unitaires_theta' in data:
            ut = data['unitaires_theta']
            state.unitaires_theta = Theta(
                C1=float(ut.get('C1', DEFAULT_THETA.C1)),
                eta1=float(ut.get('eta1', DEFAULT_THETA.eta1))
            )
        
        # Load derived metrics
        # CRITICAL FIX: Recalculate coherence from current V to avoid discontinuity
        # Old state files may have blended coherence (0.64), but we now use pure C(V)
        # Recalculate immediately to prevent discontinuity on first update
        from governance_core.coherence import coherence as coherence_func
        from governance_core.parameters import DEFAULT_PARAMS
        loaded_coherence = float(data.get('coherence', 1.0))
        # Recalculate from current V to ensure consistency
        recalculated_coherence = coherence_func(state.V, state.unitaires_theta, DEFAULT_PARAMS)
        state.coherence = float(np.clip(recalculated_coherence, 0.0, 1.0))
        state.void_active = bool(data.get('void_active', False))
        state.time = float(data.get('time', 0.0))
        state.update_count = int(data.get('update_count', 0))
        
        # Load regime tracking (backward compatible - default to "divergence")
        state.regime = str(data.get('regime', 'divergence'))
        state.regime_history = [str(r) for r in data.get('regime_history', [])]
        state.locked_persistence_count = int(data.get('locked_persistence_count', 0))
        
        # Load history arrays
        state.E_history = [float(e) for e in data.get('E_history', [])]
        state.I_history = [float(i) for i in data.get('I_history', [])]
        state.S_history = [float(s) for s in data.get('S_history', [])]
        state.V_history = [float(v) for v in data.get('V_history', [])]
        state.coherence_history = [float(c) for c in data.get('coherence_history', [])]
        state.risk_history = [float(r) for r in data.get('risk_history', [])]
        state.decision_history = list(data.get('decision_history', []))
        state.timestamp_history = list(data.get('timestamp_history', []))  # Load timestamps
        state.lambda1_history = [float(l) for l in data.get('lambda1_history', [])]  # Load lambda1 history
        
        # Load PI controller integral state (backward compatible)
        state.pi_integral = float(data.get('pi_integral', 0.0))
        
        return state
    
    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate state invariants and bounds.
        
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        # Check bounds
        if not (0.0 <= self.E <= 1.0):
            errors.append(f"E out of bounds: {self.E} (expected [0, 1])")
        if not (0.0 <= self.I <= 1.0):
            errors.append(f"I out of bounds: {self.I} (expected [0, 1])")
        if not (0.0 <= self.S <= 1.0):
            errors.append(f"S out of bounds: {self.S} (expected [0, 1])")
        if not (0.0 <= self.coherence <= 1.0):
            errors.append(f"Coherence out of bounds: {self.coherence} (expected [0, 1])")
        
        # Check for NaN/inf
        if np.isnan(self.E) or np.isinf(self.E):
            errors.append(f"E is NaN or Inf: {self.E}")
        if np.isnan(self.I) or np.isinf(self.I):
            errors.append(f"I is NaN or Inf: {self.I}")
        if np.isnan(self.S) or np.isinf(self.S):
            errors.append(f"S is NaN or Inf: {self.S}")
        if np.isnan(self.V) or np.isinf(self.V):
            errors.append(f"V is NaN or Inf: {self.V}")
        if np.isnan(self.coherence) or np.isinf(self.coherence):
            errors.append(f"Coherence is NaN or Inf: {self.coherence}")
        
        # Check lambda1 bounds
        lambda1_val = self.lambda1
        if np.isnan(lambda1_val) or np.isinf(lambda1_val):
            errors.append(f"lambda1 is NaN or Inf: {lambda1_val}")
        elif not (0.0 <= lambda1_val <= 1.0):
            errors.append(f"lambda1 out of bounds: {lambda1_val} (expected [0, 1])")
        
        # Check history consistency
        history_lengths = [
            len(self.E_history),
            len(self.I_history),
            len(self.S_history),
            len(self.V_history),
            len(self.coherence_history),
            len(self.risk_history)
        ]
        if len(set(history_lengths)) > 1:
            # Allow some variance (decision_history can be shorter)
            max_len = max(history_lengths)
            min_len = min(history_lengths)
            if max_len - min_len > 1:  # More than 1 entry difference
                errors.append(f"History length mismatch: E={len(self.E_history)}, I={len(self.I_history)}, S={len(self.S_history)}, V={len(self.V_history)}, coherence={len(self.coherence_history)}, risk={len(self.risk_history)}")
        
        return len(errors) == 0, errors

