"""
Export tool handlers.
"""

from typing import Dict, Any, Sequence
from mcp.types import TextContent
import sys
import os
import json
from datetime import datetime
from .utils import success_response, error_response, require_agent_id, require_registered_agent
from .decorators import mcp_tool
from src.governance_monitor import UNITARESMonitor
from src.logging_utils import get_logger

logger = get_logger(__name__)

# Import from mcp_server_std module
if 'src.mcp_server_std' in sys.modules:
    mcp_server = sys.modules['src.mcp_server_std']
else:
    import src.mcp_server_std as mcp_server


@mcp_tool("get_system_history", timeout=30.0)
async def handle_get_system_history(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Export complete governance history for an agent"""
    # PROACTIVE GATE: Require agent to be registered
    agent_id, error = require_registered_agent(arguments)
    if error:
        return [error]  # Returns onboarding guidance if not registered
    
    format_type = arguments.get("format", "json")
    
    # Load monitor state from disk if not in memory (consistent with get_governance_metrics)
    monitor = mcp_server.get_or_create_monitor(agent_id)
    
    history = monitor.export_history(format=format_type)
    
    return success_response({
        "format": format_type,
        "history": history
    })


@mcp_tool("export_to_file", timeout=60.0)
async def handle_export_to_file(arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Export governance history to a file in the server's data directory"""
    # PROACTIVE GATE: Require agent to be registered
    agent_id, error = require_registered_agent(arguments)
    if error:
        return [error]  # Returns onboarding guidance if not registered
    
    format_type = arguments.get("format", "json")
    custom_filename = arguments.get("filename")
    complete_package = arguments.get("complete_package", False)  # New: export all layers
    
    # Load monitor state from disk if not in memory (consistent with get_governance_metrics)
    monitor = mcp_server.get_or_create_monitor(agent_id)
    
    if complete_package:
        # Export complete package: metadata + history + validation
        # NOTE: Knowledge layer removed November 28, 2025
        
        # Get metadata
        meta = mcp_server.agent_metadata.get(agent_id)
        metadata_dict = meta.to_dict() if meta else {}
        
        # Get history (parse JSON to dict)
        history_json = monitor.export_history(format="json")
        history_dict = json.loads(history_json)
        
        # Validation checks
        # Check if state exists (monitor is loaded, state file exists, or monitor has history)
        state_exists = monitor is not None and (
            len(monitor.state.V_history) > 0 or 
            mcp_server.load_monitor_state(agent_id) is not None
        )
        
        validation_checks = {
            "metadata_exists": meta is not None,
            "history_exists": state_exists,
            "metadata_history_sync": (
                meta.total_updates == len(history_dict.get("E_history", [])) 
                if meta and history_dict else False
            )
        }
        
        # Package everything
        package = {
            "agent_id": agent_id,
            "exported_at": datetime.now().isoformat(),
            "export_type": "complete_package",
            "layers": {
                "metadata": metadata_dict,
                "history": history_dict
            },
            "validation": validation_checks
        }
        
        # Convert to requested format
        if format_type == "json":
            export_data = json.dumps(package, indent=2)
        else:
            # CSV not supported for complete package (too complex)
            return [error_response(
                "CSV format not supported for complete package export. Use 'json' format.",
                {"format": format_type, "complete_package": True}
            )]
        
        # Determine filename
        if custom_filename:
            filename = f"{custom_filename}_complete.{format_type}"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{agent_id}_complete_package_{timestamp}.{format_type}"
        
        # Use data/exports/ for complete packages
        export_dir = os.path.join(mcp_server.project_root, "data", "exports")
    else:
        # Original behavior: export history only (backward compatible)
        history_data = monitor.export_history(format=format_type)
        export_data = history_data
        
        # Determine filename
        if custom_filename:
            filename = f"{custom_filename}.{format_type}"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{agent_id}_history_{timestamp}.{format_type}"
        
        # Use data/history/ for history-only exports
        export_dir = os.path.join(mcp_server.project_root, "data", "history")
    
    os.makedirs(export_dir, exist_ok=True)
    
    # Write file
    file_path = os.path.join(export_dir, filename)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(export_data)
            f.flush()  # Ensure buffered data written
            os.fsync(f.fileno())  # Ensure written to disk
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        return success_response({
            "message": "Complete package exported successfully" if complete_package else "History exported successfully",
            "file_path": file_path,
            "filename": filename,
            "format": format_type,
            "agent_id": agent_id,
            "file_size_bytes": file_size,
            "complete_package": complete_package,
            "layers_included": ["metadata", "history", "validation"] if complete_package else ["history"]
        })
    except Exception as e:
        return [error_response(f"Failed to write file: {str(e)}", {"file_path": str(file_path)})]
