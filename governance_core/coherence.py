"""
UNITARES Governance Core - Coherence Functions

Coherence is a key feedback mechanism in UNITARES that stabilizes
the system. It depends on the void integral V and control parameters Θ.

Mathematical Definition (UNITARES v4.1 Section 3.4):
    C(V, Θ) = Cmax · 0.5 · (1 + tanh(Θ.C₁ · V))

    λ₁ = 0.3  (ethical drift into S)
    λ₂ = 0.05 (coherence coupling)

Physical Interpretation:
    - C(V, Θ) ∈ [0, Cmax] represents system coherence
    - When V → -∞: C → 0 (incoherent, I >> E)
    - When V → +∞: C → Cmax (coherent, E >> I)
    - Θ.C₁ controls the steepness of the transition
"""

import math
from .parameters import DynamicsParams, Theta


def coherence(V: float, theta: Theta, params: DynamicsParams) -> float:
    """
    Compute UNITARES coherence function (pure thermodynamic).

    C(V, Θ) = Cmax · 0.5 · (1 + tanh(Θ.C₁ · V))

    Args:
        V: Void integral (E-I imbalance accumulator)
        theta: Control parameters (C1, eta1)
        params: Dynamics parameters (for Cmax)

    Returns:
        Coherence value in [0, Cmax]

    Notes:
        - Coherence acts as a stabilizing feedback
        - Higher V (E > I) → higher coherence
        - Lower V (I > E) → lower coherence
        - C1 parameter controls transition steepness
        
    Physical Interpretation:
        - With V typically in [-0.1, 0.1] (actual operating range due to damping),
          coherence ranges approximately [0.45, 0.55]
        - Mean V ≈ -0.016 → coherence ≈ 0.49 (accurate for conservative operation)
        - This reflects genuine thermodynamic state: I slightly > E (information-preserving)
        - The narrow V range is due to high damping (δ=0.4, κ=0.3) and conservative calibration
        
    Design Decision (2025-11-27):
        - Removed coherence_scale factor for accuracy
        - Accept 0.49 coherence as honest thermodynamic signal
        - Coherence function designed for V ∈ [-2, 2] but dynamics keep V ∈ [-0.1, 0.1]
        - This is correct: system genuinely operates conservatively (I > E)
    """
    return params.Cmax * 0.5 * (1.0 + math.tanh(theta.C1 * V))


def lambda1(theta: Theta, params: DynamicsParams, lambda1_min: float = 0.05, lambda1_max: float = 0.20) -> float:
    """
    Compute λ₁ parameter (adaptive via theta.eta1).

    λ₁ is now adaptive via theta.eta1, mapped to operational range [lambda1_min, lambda1_max].
    
    Mapping: eta1 ∈ [0.1, 0.5] → lambda1 ∈ [lambda1_min, lambda1_max]
    Default range: [0.05, 0.20] per UNITARES operational bounds.

    This parameter controls how much ethical drift increases
    semantic uncertainty S.

    Args:
        theta: Control parameters (eta1 controls lambda1 adaptation)
        params: Dynamics parameters (for lambda1_base - used as fallback)
        lambda1_min: Minimum lambda1 value (default: 0.05)
        lambda1_max: Maximum lambda1 value (default: 0.20)

    Returns:
        λ₁ value (drift → S coupling strength) in [lambda1_min, lambda1_max]

    Notes:
        - Adaptive lambda1 via PI controller (enables adaptive control)
        - Maps theta.eta1 [0.1, 0.5] → lambda1 [lambda1_min, lambda1_max]
        - Linear mapping: lambda1 = lambda1_min + (eta1 - 0.1) / (0.5 - 0.1) * (lambda1_max - lambda1_min)
        - Falls back to lambda1_base if eta1 outside expected range
        
    Historical:
        - 2025-11-26: Fixed bug where eta1 was incorrectly multiplied (0.3 * 0.3 = 0.09)
        - 2025-11-28: Made adaptive via eta1 mapping to enable PI controller adaptation
    """
    # Map eta1 [0.1, 0.5] → lambda1 [lambda1_min, lambda1_max]
    # Linear interpolation
    eta1_min = 0.1
    eta1_max = 0.5
    eta1_range = eta1_max - eta1_min
    lambda1_range = lambda1_max - lambda1_min
    
    # Clamp eta1 to expected range
    eta1_clamped = max(eta1_min, min(eta1_max, theta.eta1))
    
    # Linear mapping
    if eta1_range > 0:
        normalized_eta1 = (eta1_clamped - eta1_min) / eta1_range
        adaptive_lambda1 = lambda1_min + normalized_eta1 * lambda1_range
    else:
        # Fallback if range is zero
        adaptive_lambda1 = params.lambda1_base
    
    return adaptive_lambda1


def lambda2(theta: Theta, params: DynamicsParams) -> float:
    """
    Compute λ₂ parameter.

    λ₂(Θ) = λ₂_base

    This parameter controls how much coherence reduces
    semantic uncertainty S.

    Args:
        theta: Control parameters (unused in current implementation)
        params: Dynamics parameters (for lambda2_base)

    Returns:
        λ₂ value (coherence → S reduction strength)

    Notes:
        - Currently not Theta-dependent
        - Could be extended to λ₂(Θ) = θ.η₂ · λ₂_base
    """
    return params.lambda2_base
