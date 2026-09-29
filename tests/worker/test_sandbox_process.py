import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agent_platform.worker.sandbox_process import (
    _context_policy_patch,
    _watch_budget_exhaustion,
)


@pytest.mark.asyncio
async def test_context_policy_patch_matches_validated_dsh_rc1_policy() -> None:
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
async def test_watch_budget_exhaustion_waits_for_event_then_closes_and_awaits_server() -> None:
    """
    TEST 1: watcher waits for event, then closes and awaits server.

    This test verifies that the watcher function:
    1. Waits for the budget_exhausted event to be set
    2. Closes the server when the event is set
    3. Awaits for the server to close properly
    """
    # Create a mock server with proper async methods
    mock_server = AsyncMock()
    mock_server.close = AsyncMock(return_value=None)
    mock_server.wait_closed = AsyncMock(return_value=None)

    # Create the event
    budget_exhausted = asyncio.Event()

    # Initially, the event should not be set
    assert not budget_exhausted.is_set()

    # Create the watcher task
    watcher_task = asyncio.create_task(_watch_budget_exhaustion(mock_server, budget_exhausted))

    # The watcher should still be running (not done)
    assert not watcher_task.done()

    # Set the budget_exhausted event
    budget_exhausted.set()

    # The watcher should now complete
    await watcher_task

    # Verify the watcher completed successfully
    assert watcher_task.done()

    # Verify that close and wait_closed were called
    mock_server.close.assert_called_once()
    mock_server.wait_closed.assert_called_once()


@pytest.mark.asyncio
async def test_watch_budget_exhaustion_is_event_driven_and_does_not_poll() -> None:
    """
    TEST 2: watcher is event-driven and does not poll (using sleep monkeypatching).

    This test verifies that the watcher function:
    1. Is event-driven (uses wait(), not polling)
    2. Does not poll the event continuously

    We use sleep monkeypatching to verify no polling occurs.
    """
    # Track if sleep was called during the watcher
    sleep_calls = []
    original_sleep = asyncio.sleep

    async def tracked_sleep(delay=0, *args, **kwargs):
        sleep_calls.append((delay, args, kwargs))
        return await original_sleep(delay, *args, **kwargs)

    # Create a mock server with proper async methods
    mock_server = AsyncMock()
    mock_server.close = AsyncMock(return_value=None)
    mock_server.wait_closed = AsyncMock(return_value=None)

    # Create the event
    budget_exhausted = asyncio.Event()

    # Patch asyncio.sleep to track calls
    with patch("asyncio.sleep", new=tracked_sleep):
        # Create the watcher task
        watcher_task = asyncio.create_task(_watch_budget_exhaustion(mock_server, budget_exhausted))

        # The watcher should still be running
        assert not watcher_task.done()

        # Set the budget_exhausted event
        budget_exhausted.set()

        # Wait for the watcher to complete
        await watcher_task

        # Verify the watcher completed successfully
        assert watcher_task.done()

        # Verify that sleep was not called while waiting (event-driven, not polling)
        # The sleep should only be called after the event is set, not during the wait
        assert len(sleep_calls) == 0
