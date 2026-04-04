"""Shared operator-facing semantics for primary, behavioral, and ODE EISV views."""

from __future__ import annotations

from typing import Dict


STATE_SEMANTICS: Dict[str, str] = {
    "flat_fields": "Flat E/I/S/V fields and the `eisv` object refer to `primary_eisv`.",
    "primary_eisv": "Default state view for operators. Uses behavioral EISV when confidence is sufficient, otherwise falls back to ODE.",
    "primary_eisv_source": "Indicates where the primary EISV came from: `behavioral`, `ode_fallback`, or `legacy_flat` for old persisted rows.",
    "behavioral_eisv": "Observation-first agent state derived from live behavior. This is the preferred proprioceptive state.",
    "ode_eisv": "Parallel ODE state vector retained for continuity and fallback, not the default operator view.",
    "ode_diagnostics": "Control-layer diagnostics derived from ODE state, including phi, coherence, regime, lambda1, and ODE-side verdict/risk.",
}


def get_state_semantics() -> Dict[str, str]:
    """Return a copy so callers can attach semantics without shared mutation."""
    return dict(STATE_SEMANTICS)
