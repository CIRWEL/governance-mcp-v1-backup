"""
Compatibility wrapper for CLI bridge - provides JSON-RPC interface to mcp_server_std handlers

This allows the CLI bridge to use the full v2.0 server instead of the old v1.0 stub.
"""

import asyncio
import json
from typing import Dict, Any
from datetime import datetime

# Import the handler dispatcher from mcp_server_std
from src.mcp_handlers import dispatch_tool
from mcp.types import TextContent


class GovernanceMCPServer:
    """
    Compatibility wrapper for CLI bridge.
    
    Provides JSON-RPC style interface that calls the full v2.0 MCP handlers.
    This gives CLI users access to all 47+ tools, not just the 4 basic ones.
    """
    
    def __init__(self):
        """Initialize compatibility server"""
        # Use logging utility for consistency
        from src.logging_utils import get_logger
        logger = get_logger(__name__)
        logger.info("Compatibility server initialized (using v2.0 handlers)")
    
    def _convert_response_to_dict(self, text_contents: Any) -> Dict:
        """
        Convert MCP TextContent response to dict format expected by bridge.
        
        Handlers return Sequence[TextContent], but bridge expects dict with 'success', etc.
        """
        if not text_contents:
            return {
                'success': False,
                'error': 'No response from handler',
                'timestamp': datetime.now().isoformat()
            }
        
        # Handle both list and single TextContent
        if isinstance(text_contents, list) and len(text_contents) > 0:
            # Extract text from first TextContent
            response_text = text_contents[0].text
        elif hasattr(text_contents, 'text'):
            # Single TextContent object
            response_text = text_contents.text
        elif isinstance(text_contents, str):
            # Already a string
            response_text = text_contents
        else:
            return {
                'success': False,
                'error': f'Unexpected response format: {type(text_contents)}',
                'timestamp': datetime.now().isoformat()
            }
        
        # Try to parse as JSON (most handlers return JSON)
        try:
            result = json.loads(response_text)
            # Ensure it has 'success' field for bridge compatibility
            if 'success' not in result:
                result['success'] = True
            return result
        except json.JSONDecodeError:
            # If not JSON, wrap in success response
            return {
                'success': True,
                'message': response_text,
                'timestamp': datetime.now().isoformat()
            }
    
    def _run_async_handler(self, tool_name: str, params: Dict) -> Dict:
        """
        Run async handler synchronously (for bridge compatibility).
        
        Bridge expects synchronous interface, but handlers are async.
        """
        try:
            # Run async handler in event loop
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop running - create new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run handler
        try:
            result = loop.run_until_complete(dispatch_tool(tool_name, params))
            return self._convert_response_to_dict(result)
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def tool_process_agent_update(self, params: Dict) -> Dict:
        """Tool: process_agent_update - compatibility wrapper"""
        return self._run_async_handler('process_agent_update', params)
    
    def tool_get_governance_metrics(self, params: Dict) -> Dict:
        """Tool: get_governance_metrics - compatibility wrapper"""
        return self._run_async_handler('get_governance_metrics', params)
    
    def tool_get_system_history(self, params: Dict) -> Dict:
        """Tool: get_system_history - compatibility wrapper"""
        return self._run_async_handler('get_system_history', params)
    
    def tool_reset_monitor(self, params: Dict) -> Dict:
        """Tool: reset_monitor - compatibility wrapper"""
        return self._run_async_handler('reset_monitor', params)
    
    def list_tools(self) -> Dict:
        """Returns list of all available tools (43+ tools)"""
        # Call the actual list_tools handler - this returns all registered tools
        result = self._run_async_handler('list_tools', {})
        if result.get('success'):
            # Handler returns full tool list with categories, relationships, etc.
            return result
        else:
            # Fallback: Get tools from actual handler registry
            try:
                from src.mcp_handlers import TOOL_HANDLERS
                registered_tools = sorted(TOOL_HANDLERS.keys())
                return {
                    'success': True,
                    'tools': [
                        {'name': name, 'description': f'Tool: {name}'}
                        for name in registered_tools
                    ],
                    'total_tools': len(registered_tools),
                    'message': f'Found {len(registered_tools)} registered tools'
                }
            except Exception as e:
                # Last resort: return basic list
                return {
                    'success': False,
                    'error': f'Could not list tools: {e}',
                    'tools': [
                        {
                            'name': 'process_agent_update',
                            'description': 'Run one complete governance cycle',
                            'parameters': ['agent_id', 'api_key', 'parameters', 'ethical_drift', 'response_text', 'complexity']
                        },
                        {
                            'name': 'get_governance_metrics',
                            'description': 'Get current governance state',
                            'parameters': ['agent_id']
                        },
                        {
                            'name': 'get_system_history',
                            'description': 'Export time series data',
                            'parameters': ['agent_id', 'format']
                        },
                        {
                            'name': 'reset_monitor',
                            'description': 'Reset governance state',
                            'parameters': ['agent_id']
                        }
                    ],
                    'message': 'Using fallback list - call list_tools handler for full list'
                }
    
    def handle_request(self, request: Dict) -> Dict:
        """
        Main request handler for JSON-RPC style interface.
        
        Request format:
        {
            'tool': 'tool_name',
            'params': {...}
        }
        
        Now uses full v2.0 handlers instead of old v1.0 stub!
        """
        tool_name = request.get('tool')
        params = request.get('params', {})
        
        # Map old tool names to new ones (if needed)
        tool_mapping = {
            'process_agent_update': 'process_agent_update',
            'get_governance_metrics': 'get_governance_metrics',
            'get_system_history': 'get_system_history',
            'reset_monitor': 'reset_monitor',
            'list_tools': 'list_tools'
        }
        
        # Use mapped name if available, otherwise use original
        mapped_name = tool_mapping.get(tool_name, tool_name)
        
        # Call handler via compatibility wrapper
        if mapped_name == 'list_tools':
            return self.list_tools()
        elif mapped_name == 'process_agent_update':
            return self.tool_process_agent_update(params)
        elif mapped_name == 'get_governance_metrics':
            return self.tool_get_governance_metrics(params)
        elif mapped_name == 'get_system_history':
            return self.tool_get_system_history(params)
        elif mapped_name == 'reset_monitor':
            return self.tool_reset_monitor(params)
        else:
            # Try calling directly (might be a new tool not in mapping)
            return self._run_async_handler(mapped_name, params)

