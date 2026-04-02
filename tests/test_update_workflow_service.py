from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.update_workflow_service import run_process_update_workflow
from tests.helpers import parse_result


class _DummyLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_run_process_update_workflow_happy_path():
    ctx = SimpleNamespace(
        mcp_server=MagicMock(),
        agent_id="agent-123",
        agent_uuid="uuid-123",
        arguments={},
        identity_assurance={"tier": "strong"},
        result={"status": "ok"},
        meta=None,
        is_new_agent=False,
        key_was_generated=False,
        api_key_auto_retrieved=False,
        task_type="mixed",
        loop=AsyncMock(),
    )
    ctx.mcp_server.lock_manager.acquire_agent_lock_async.return_value = _DummyLock()
    ctx.mcp_server.monitors = {"agent-123": {"dummy": True}}

    with patch("src.mcp_handlers.updates.phases.resolve_identity_and_guards", new=AsyncMock(return_value=None)), \
         patch("src.mcp_handlers.updates.phases.handle_onboarding_and_resume", new=AsyncMock(return_value=None)), \
         patch("src.mcp_handlers.updates.phases.transform_inputs", return_value=None), \
         patch("src.mcp_handlers.updates.phases.execute_locked_update", new=AsyncMock(return_value=None)), \
         patch("src.mcp_handlers.updates.phases.execute_post_update_effects", new=AsyncMock()), \
         patch("src.mcp_handlers.updates.pipeline.run_enrichment_pipeline", new=AsyncMock()), \
         patch("src.mcp_handlers.response_formatter.format_response", return_value={"status": "formatted"}), \
         patch("src.services.update_workflow_service.serialize_process_update_response", return_value=["done"]) as mock_serialize:
        result = await run_process_update_workflow(ctx)

    assert result == ["done"]
    mock_serialize.assert_called_once()
    assert ctx.monitor == {"dummy": True}


@pytest.mark.asyncio
async def test_run_process_update_workflow_returns_early_exit():
    ctx = SimpleNamespace(
        mcp_server=MagicMock(),
        arguments={},
    )
    early = ["stop"]
    with patch("src.mcp_handlers.updates.phases.resolve_identity_and_guards", new=AsyncMock(return_value=early)):
        result = await run_process_update_workflow(ctx)
    assert result == early


@pytest.mark.asyncio
async def test_run_process_update_workflow_timeout_uses_lock_error_category():
    class _TimeoutLockManager:
        def acquire_agent_lock_async(self, *args, **kwargs):
            raise TimeoutError("lock timeout")

    ctx = SimpleNamespace(
        mcp_server=MagicMock(lock_manager=_TimeoutLockManager()),
        agent_id="agent-123",
        agent_uuid="uuid-123",
        arguments={"client_session_id": "agent-123"},
        identity_assurance={"tier": "strong"},
        result={},
        meta=None,
        is_new_agent=False,
        key_was_generated=False,
        api_key_auto_retrieved=False,
        task_type="mixed",
        loop=AsyncMock(),
    )

    with patch("src.mcp_handlers.updates.phases.resolve_identity_and_guards", new=AsyncMock(return_value=None)), \
         patch("src.mcp_handlers.updates.phases.handle_onboarding_and_resume", new=AsyncMock(return_value=None)), \
         patch("src.mcp_handlers.updates.phases.transform_inputs", return_value=None), \
         patch("src.lock_cleanup.cleanup_stale_state_locks", return_value={"cleaned": 0}):
        result = await run_process_update_workflow(ctx)

    data = parse_result(result)
    assert data["error_code"] == "LOCK_TIMEOUT"
    assert data["error_category"] == "system_error"
    assert data["lock_error"] is True
