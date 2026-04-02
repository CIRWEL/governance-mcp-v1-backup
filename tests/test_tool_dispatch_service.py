from unittest.mock import AsyncMock, patch

import pytest

from src.services.tool_dispatch_service import run_tool_dispatch_pipeline


@pytest.mark.asyncio
async def test_run_tool_dispatch_pipeline_executes_handler_after_steps():
    step = AsyncMock(side_effect=lambda n, a, c: (n, a, c))
    handler = AsyncMock(return_value=["ok"])

    with patch("src.mcp_handlers.TOOL_HANDLERS", {"demo": handler}):
        result = await run_tool_dispatch_pipeline(
            name="demo",
            arguments={"x": 1},
            pre_steps=[step],
            post_steps=[],
        )

    assert result == ["ok"]
    handler.assert_awaited_once_with({"x": 1})


@pytest.mark.asyncio
async def test_run_tool_dispatch_pipeline_returns_tool_not_found():
    result = await run_tool_dispatch_pipeline(
        name="missing_demo_tool",
        arguments={},
        pre_steps=[],
        post_steps=[],
    )
    assert isinstance(result, list)
