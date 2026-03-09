"""Admin — server management, dashboard, config, calibration."""

from .handlers import (
    handle_reset_monitor,
    handle_get_server_info,
    handle_health_check,
    handle_get_connection_status,
    handle_get_telemetry_metrics,
    handle_cleanup_stale_locks,
    handle_get_workspace_health,
    handle_get_tool_usage_stats,
    handle_validate_file_path,
)
from .dashboard import handle_dashboard
from .config import handle_get_thresholds, handle_set_thresholds
from .calibration import (
    handle_check_calibration,
    handle_rebuild_calibration,
    handle_update_calibration_ground_truth,
    handle_backfill_calibration_from_dialectic,
)

__all__ = [
    "handle_reset_monitor",
    "handle_get_server_info",
    "handle_health_check",
    "handle_get_connection_status",
    "handle_get_telemetry_metrics",
    "handle_cleanup_stale_locks",
    "handle_get_workspace_health",
    "handle_get_tool_usage_stats",
    "handle_validate_file_path",
    "handle_dashboard",
    "handle_get_thresholds",
    "handle_set_thresholds",
    "handle_check_calibration",
    "handle_rebuild_calibration",
    "handle_update_calibration_ground_truth",
    "handle_backfill_calibration_from_dialectic",
]
