"""
Parameter validation helpers for MCP tool handlers.

Provides consistent validation for common parameter types (enums, ranges, formats)
with helpful error messages for agents.
"""

from typing import Dict, Any, Optional, Tuple, List
from mcp.types import TextContent
from .utils import error_response


# Enum definitions for validation
DISCOVERY_TYPES = {"bug_found", "insight", "pattern", "improvement", "question", "answer", "note"}
SEVERITY_LEVELS = {"low", "medium", "high", "critical"}
DISCOVERY_STATUSES = {"open", "resolved", "archived", "disputed"}
TASK_TYPES = {"convergent", "divergent", "mixed"}
RESPONSE_TYPES = {"extend", "question", "disagree", "support"}
LIFECYCLE_STATUSES = {"active", "waiting_input", "paused", "archived", "deleted"}
HEALTH_STATUSES = {"healthy", "moderate", "critical", "unknown"}


def validate_enum(
    value: Any,
    valid_values: set,
    param_name: str,
    suggestions: Optional[List[str]] = None
) -> Tuple[Optional[str], Optional[TextContent]]:
    """
    Validate an enum parameter value.
    
    Args:
        value: The value to validate
        valid_values: Set of valid enum values
        param_name: Name of the parameter (for error messages)
        suggestions: Optional list of suggested values (for typo detection)
        
    Returns:
        Tuple of (validated_value, error_response). If value is invalid, error_response is provided.
    """
    if value is None:
        return None, None  # None is allowed (optional parameters)
    
    if value not in valid_values:
        # Try to find close matches for typo detection
        close_matches = []
        if suggestions:
            value_lower = str(value).lower()
            for suggestion in suggestions:
                if value_lower in suggestion.lower() or suggestion.lower() in value_lower:
                    close_matches.append(suggestion)
        
        error_msg = f"Invalid {param_name}: '{value}'. Must be one of: {', '.join(sorted(valid_values))}"
        if close_matches:
            error_msg += f". Did you mean: {', '.join(close_matches)}?"
        
        return None, error_response(
            error_msg,
            details={"error_type": "invalid_enum", "param_name": param_name, "provided_value": value},
            recovery={
                "action": f"Use one of the valid {param_name} values",
                "related_tools": ["list_tools"],
                "workflow": [
                    f"1. Check tool description for valid {param_name} values",
                    f"2. Use one of: {', '.join(sorted(valid_values))}",
                    "3. Retry with correct value"
                ]
            }
        )
    
    return value, None


def validate_discovery_type(value: Any) -> Tuple[Optional[str], Optional[TextContent]]:
    """Validate discovery_type parameter."""
    return validate_enum(value, DISCOVERY_TYPES, "discovery_type", list(DISCOVERY_TYPES))


def validate_severity(value: Any) -> Tuple[Optional[str], Optional[TextContent]]:
    """Validate severity parameter."""
    return validate_enum(value, SEVERITY_LEVELS, "severity", list(SEVERITY_LEVELS))


def validate_discovery_status(value: Any) -> Tuple[Optional[str], Optional[TextContent]]:
    """Validate discovery status parameter."""
    return validate_enum(value, DISCOVERY_STATUSES, "status", list(DISCOVERY_STATUSES))


def validate_task_type(value: Any) -> Tuple[Optional[str], Optional[TextContent]]:
    """Validate task_type parameter."""
    return validate_enum(value, TASK_TYPES, "task_type", list(TASK_TYPES))


def validate_response_type(value: Any) -> Tuple[Optional[str], Optional[TextContent]]:
    """Validate response_type parameter."""
    return validate_enum(value, RESPONSE_TYPES, "response_type", list(RESPONSE_TYPES))


def validate_lifecycle_status(value: Any) -> Tuple[Optional[str], Optional[TextContent]]:
    """Validate lifecycle_status parameter."""
    return validate_enum(value, LIFECYCLE_STATUSES, "lifecycle_status", list(LIFECYCLE_STATUSES))


def validate_health_status(value: Any) -> Tuple[Optional[str], Optional[TextContent]]:
    """Validate health_status parameter."""
    return validate_enum(value, HEALTH_STATUSES, "health_status", list(HEALTH_STATUSES))


def validate_range(
    value: Any,
    min_val: float,
    max_val: float,
    param_name: str,
    inclusive: bool = True
) -> Tuple[Optional[float], Optional[TextContent]]:
    """
    Validate a numeric parameter is within a range.
    
    Args:
        value: The value to validate
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        param_name: Name of the parameter (for error messages)
        inclusive: If True, range is [min, max]. If False, range is (min, max).
        
    Returns:
        Tuple of (validated_value, error_response). If value is invalid, error_response is provided.
    """
    if value is None:
        return None, None  # None is allowed (optional parameters)
    
    try:
        num_value = float(value)
    except (TypeError, ValueError):
        return None, error_response(
            f"Invalid {param_name}: '{value}'. Must be a number.",
            details={"error_type": "invalid_type", "param_name": param_name, "provided_value": value},
            recovery={
                "action": f"Provide a numeric value for {param_name}",
                "workflow": [f"1. Ensure {param_name} is a number", "2. Retry with correct value"]
            }
        )
    
    if inclusive:
        if not (min_val <= num_value <= max_val):
            return None, error_response(
                f"Invalid {param_name}: {num_value}. Must be in range [{min_val}, {max_val}].",
                details={"error_type": "out_of_range", "param_name": param_name, "provided_value": num_value, "valid_range": [min_val, max_val]},
                recovery={
                    "action": f"Provide a value between {min_val} and {max_val}",
                    "workflow": [f"1. Ensure {param_name} is in [{min_val}, {max_val}]", "2. Retry with correct value"]
                }
            )
    else:
        if not (min_val < num_value < max_val):
            return None, error_response(
                f"Invalid {param_name}: {num_value}. Must be in range ({min_val}, {max_val}).",
                details={"error_type": "out_of_range", "param_name": param_name, "provided_value": num_value, "valid_range": (min_val, max_val)},
                recovery={
                    "action": f"Provide a value between {min_val} and {max_val} (exclusive)",
                    "workflow": [f"1. Ensure {param_name} is in ({min_val}, {max_val})", "2. Retry with correct value"]
                }
            )
    
    return num_value, None


def validate_complexity(value: Any) -> Tuple[Optional[float], Optional[TextContent]]:
    """Validate complexity parameter (0.0 to 1.0)."""
    return validate_range(value, 0.0, 1.0, "complexity")


def validate_confidence(value: Any) -> Tuple[Optional[float], Optional[TextContent]]:
    """Validate confidence parameter (0.0 to 1.0)."""
    return validate_range(value, 0.0, 1.0, "confidence")


def validate_ethical_drift(value: Any) -> Tuple[Optional[List[float]], Optional[TextContent]]:
    """
    Validate ethical_drift parameter (list of 3 floats).
    
    Args:
        value: Should be a list of 3 numbers
        
    Returns:
        Tuple of (validated_list, error_response)
    """
    if value is None:
        return None, None  # None is allowed (optional)
    
    if not isinstance(value, list):
        return None, error_response(
            f"Invalid ethical_drift: must be a list of 3 numbers, got {type(value).__name__}",
            details={"error_type": "invalid_type", "param_name": "ethical_drift", "provided_value": value},
            recovery={
                "action": "Provide ethical_drift as a list of 3 numbers: [primary_drift, coherence_loss, complexity_contribution]",
                "workflow": ["1. Format as list: [0.01, 0.02, 0.03]", "2. Retry with correct format"]
            }
        )
    
    if len(value) != 3:
        return None, error_response(
            f"Invalid ethical_drift: must have exactly 3 components, got {len(value)}",
            details={"error_type": "invalid_length", "param_name": "ethical_drift", "provided_value": value},
            recovery={
                "action": "Provide exactly 3 numbers: [primary_drift, coherence_loss, complexity_contribution]",
                "workflow": ["1. Format as list of 3 numbers: [0.01, 0.02, 0.03]", "2. Retry with correct format"]
            }
        )
    
    # Validate each component is numeric
    validated = []
    for i, component in enumerate(value):
        num_value, error = validate_range(component, -1.0, 1.0, f"ethical_drift[{i}]")
        if error:
            return None, error
        validated.append(num_value)
    
    return validated, None

