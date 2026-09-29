import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

import agent_platform.worker.sandbox_process as sandbox_process
from agent_platform.worker.execution_budget import ModelCallBudget, ModelCallBudgetExceededError
from agent_platform.worker.sandbox_process import (
    _context_policy_patch,
    _watch_budget_exhaustion,
)


def test_context_policy_patch_matches_validated_dsh_rc1_policy() -> None:
    patch = _context_policy_patch(
        context_window=4096,
        max_output_tokens=1024,
    )

    assert patch == (
        "- id: llm-deepseek\n"
        "  config:\n"
        "    apiKeyEnv: DEEPSEEK_API_KEY\n"
        "    defaultContextWindow: 4096\n"
        "    maxTokens: 1024\n"
        "    streamIdleTimeoutMs: 172800000\n"
        "\n"
        "- insert:\n"
        "    - id: token-meter\n"
        "      name: '@deepseek-ai/dsh-token-meter'\n"
        "\n"
        "    - id: compaction-basic\n"
        "      name: '@deepseek-ai/dsh-compaction-basic'\n"
        "      config:\n"
        "        thresholdRatio: 0.55\n"
        "        retainTokens: 1024\n"
        "        maxTokens: 768\n"
        "        compactionRetries: 1\n"
        "        maxOverflowRetries: 1\n"
        "        auto: true\n"
    )

    assert "headroomTokens" not in patch


@pytest.mark.asyncio
async def test_watch_budget_exhaustion_on_event_set() -> None:
    event = asyncio.Event()
    server = Mock()
    server.close = Mock()
    server.wait_closed = AsyncMock()

    watcher_task = asyncio.create_task(_watch_budget_exhaustion(server, event))

    await asyncio.sleep(0)

    assert not watcher_task.done()
    server.close.assert_not_called()
    server.wait_closed.assert_not_awaited()

    event.set()

    await watcher_task

    server.close.assert_called_once()
    server.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_watch_budget_exhaustion_with_monkeypatched_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = asyncio.Event()
    server = Mock()
    server.close = Mock()
    server.wait_closed = AsyncMock()

    async def forbidden_sleep(*args, **kwargs) -> None:
        raise AssertionError("polling is forbidden")

    monkeypatch.setattr(sandbox_process.asyncio, "sleep", forbidden_sleep)

    asyncio.get_running_loop().call_soon(event.set)

    await _watch_budget_exhaustion(server, event)

    server.close.assert_called_once()
    server.wait_closed.assert_awaited_once()


def test_proxy_budget_boundary_allows_32_and_blocks_33() -> None:
    budget = ModelCallBudget(max_calls=32)

    # Verify 32 calls are allowed (boundary case)
    for _ in range(32):
        budget.consume()

    assert budget.consumed_calls == 32
    assert budget.remaining_calls == 0

    # The 33rd call should raise ModelCallBudgetExceededError
    with pytest.raises(ModelCallBudgetExceededError):
        budget.consume()

    # After the exception, consumed_calls should still be 32
    assert budget.consumed_calls == 32
