from unittest.mock import AsyncMock, patch

import pytest

from src.services.http_dispatch_fallback import execute_http_dispatch_fallback


@pytest.mark.asyncio
async def test_http_dispatch_fallback_runs_handler_without_dispatch_identity_step():
    handler = AsyncMock(return_value=["ok"])

    with patch("src.mcp_handlers.TOOL_HANDLERS", {"demo_tool": handler}), \
         patch("src.mcp_handlers.middleware.trajectory_step.verify_trajectory", new=AsyncMock(side_effect=lambda n, a, c: (n, a, c))), \
         patch("src.mcp_handlers.middleware.params_step.unwrap_kwargs", new=AsyncMock(side_effect=lambda n, a, c: (n, a, c))), \
         patch("src.mcp_handlers.middleware.params_step.resolve_alias", new=AsyncMock(side_effect=lambda n, a, c: (n, a, c))), \
         patch("src.mcp_handlers.middleware.params_step.inject_identity", new=AsyncMock(side_effect=lambda n, a, c: (n, a, c))), \
         patch("src.mcp_handlers.middleware.params_step.validate_params", new=AsyncMock(side_effect=lambda n, a, c: (n, a, c))), \
         patch("src.mcp_handlers.middleware.POST_VALIDATION_STEPS", []):
        result = await execute_http_dispatch_fallback("demo_tool", {"x": 1})

    assert result == ["ok"]
    handler.assert_awaited_once_with({"x": 1})
