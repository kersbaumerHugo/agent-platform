from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from agent_platform.worker.sandbox_process import _context_policy_patch, _watch_budget_exhaustion


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
async def test_watch_budget_exhaustion_with_async_sleep() -> None:
    """Test _watch_budget_exhaustion with asyncio.Event initially unset."""
    event = asyncio.Event()
    server = AsyncMock(spec=asyncio.Server)
    server.close = Mock()
    server.wait_closed = AsyncMock()

    watcher_task = asyncio.create_task(_watch_budget_exhaustion(server, event))
    await asyncio.sleep(0)

    assert not watcher_task.done()
    assert server.close.call_count == 0
    assert server.wait_closed.await_count == 0

    event.set()
    await watcher_task

    assert server.close.call_count == 1
    assert server.wait_closed.await_count == 1


@pytest.mark.asyncio
async def test_watch_budget_exhaustion_with_forbidden_sleep() -> None:
    """Test _watch_budget_exhaustion with forbidden sleep pattern."""
    event = asyncio.Event()
    server = AsyncMock(spec=asyncio.Server)
    server.close = Mock()
    server.wait_closed = AsyncMock()

    async def forbidden_sleep(*args, **kwargs):
        raise AssertionError("polling is forbidden")

    agent_platform = __import__("agent_platform", fromlist=["worker"])
    agent_platform.worker.sandbox_process.asyncio.sleep = forbidden_sleep

    loop = asyncio.get_running_loop()
    loop.call_soon(event.set)

    await _watch_budget_exhaustion(server, event)

    assert server.close.call_count == 1
    assert server.wait_closed.await_count == 1
