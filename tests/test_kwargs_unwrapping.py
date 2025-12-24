"""
Tests for kwargs unwrapping behavior across dispatch and direct handler calls.
"""

import sys
import json
import uuid
from pathlib import Path
import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def _make_unique_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@pytest.mark.asyncio
async def test_dispatch_tool_kwargs_string_unwrap():
    """dispatch_tool should unwrap kwargs when provided as a JSON string."""
    from src.mcp_handlers import dispatch_tool

    name = _make_unique_name("test_kwargs_str")
    result = await dispatch_tool("identity", {"kwargs": json.dumps({"name": name})})
    assert result, "Expected a response from identity"

    data = json.loads(result[0].text)
    assert data.get("success") is True
    assert data.get("name_updated") is True
    assert data.get("agent_id") == name


@pytest.mark.asyncio
async def test_dispatch_tool_kwargs_dict_unwrap():
    """dispatch_tool should unwrap kwargs when already parsed into a dict."""
    from src.mcp_handlers import dispatch_tool

    name = _make_unique_name("test_kwargs_dict")
    result = await dispatch_tool("identity", {"kwargs": {"name": name}})
    assert result, "Expected a response from identity"

    data = json.loads(result[0].text)
    assert data.get("success") is True
    assert data.get("name_updated") is True
    assert data.get("agent_id") == name


@pytest.mark.asyncio
async def test_handle_identity_kwargs_dict_direct():
    """handle_identity should unwrap kwargs dicts when bypassing dispatch_tool."""
    from src.mcp_handlers.identity import handle_identity

    name = _make_unique_name("test_kwargs_direct")
    result = await handle_identity({"kwargs": {"name": name}})
    assert result, "Expected a response from identity"

    data = json.loads(result[0].text)
    assert data.get("success") is True
    assert data.get("name_updated") is True
    assert data.get("agent_id") == name
