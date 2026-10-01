import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

import agent_platform.worker.sandbox_process as sandbox_process
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
        "    - id: tool-result-pruner\n"
        "      name: '@deepseek-ai/dsh-compaction-tool-result-pruner'\n"
        "      config:\n"
        "        thresholdChars: 8192\n"
        "        headChars: 4096\n"
        "        tailChars: 1024\n"
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


@pytest.mark.asyncio
async def test_worker_self_repair_runs_once_after_failed_self_verification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from agent_platform.worker.self_verification import (
        WorkerSelfVerificationResult,
    )

    calls = []

    class Executor:
        async def execute(self, request):
            calls.append(request)
            return sandbox_process.WorkerExecutionResult(
                summary=f"attempt-{len(calls)}",
            )

    hygiene = AsyncMock()

    verification_results = [
        WorkerSelfVerificationResult(
            command=("python", "-m", "pytest", "-q"),
            exit_code=1,
            output="3 failed",
        ),
        WorkerSelfVerificationResult(
            command=("python", "-m", "pytest", "-q"),
            exit_code=0,
            output="500 passed",
        ),
    ]

    verifier = AsyncMock(
        side_effect=verification_results,
    )

    monkeypatch.setattr(
        sandbox_process,
        "apply_workspace_hygiene",
        hygiene,
    )
    monkeypatch.setattr(
        sandbox_process,
        "run_worker_self_verification",
        verifier,
    )

    result = await sandbox_process._execute_with_bounded_self_repair(
        executor=Executor(),
        goal="Implement the requested change.",
        workspace=tmp_path,
    )

    assert result.summary == "attempt-2"
    assert len(calls) == 2
    assert "single bounded self-repair attempt" in calls[1].goal
    assert "3 failed" in calls[1].goal
    assert hygiene.await_count == 2
    assert verifier.await_count == 2


@pytest.mark.asyncio
async def test_worker_does_not_repair_when_self_verification_passes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from agent_platform.worker.self_verification import (
        WorkerSelfVerificationResult,
    )

    calls = []

    class Executor:
        async def execute(self, request):
            calls.append(request)
            return sandbox_process.WorkerExecutionResult(
                summary="done",
            )

    hygiene = AsyncMock()
    verifier = AsyncMock(
        return_value=WorkerSelfVerificationResult(
            command=("python", "-m", "pytest", "-q"),
            exit_code=0,
            output="500 passed",
        )
    )

    monkeypatch.setattr(
        sandbox_process,
        "apply_workspace_hygiene",
        hygiene,
    )
    monkeypatch.setattr(
        sandbox_process,
        "run_worker_self_verification",
        verifier,
    )

    result = await sandbox_process._execute_with_bounded_self_repair(
        executor=Executor(),
        goal="Implement the requested change.",
        workspace=tmp_path,
    )

    assert result.summary == "done"
    assert len(calls) == 1
    hygiene.assert_awaited_once()
    verifier.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_self_repair_stops_after_exactly_one_failed_repair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from agent_platform.worker.self_verification import (
        WorkerSelfVerificationResult,
    )

    calls = []

    class Executor:
        async def execute(self, request):
            calls.append(request)
            return sandbox_process.WorkerExecutionResult(
                summary=f"attempt-{len(calls)}",
            )

    hygiene = AsyncMock()

    verifier = AsyncMock(
        side_effect=[
            WorkerSelfVerificationResult(
                command=("python", "-m", "pytest", "-q"),
                exit_code=1,
                output="3 failed",
            ),
            WorkerSelfVerificationResult(
                command=("python", "-m", "pytest", "-q"),
                exit_code=1,
                output="1 failed",
            ),
        ],
    )

    monkeypatch.setattr(
        sandbox_process,
        "apply_workspace_hygiene",
        hygiene,
    )
    monkeypatch.setattr(
        sandbox_process,
        "run_worker_self_verification",
        verifier,
    )

    result = await sandbox_process._execute_with_bounded_self_repair(
        executor=Executor(),
        goal="Implement the requested change.",
        workspace=tmp_path,
    )

    assert len(calls) == 2
    assert hygiene.await_count == 2
    assert verifier.await_count == 2
    assert "remains failing" in result.summary
    assert "authoritative trusted verification" in result.summary


@pytest.mark.asyncio
async def test_phase_limited_initial_attempt_still_runs_one_repair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from agent_platform.worker.self_verification import (
        WorkerSelfVerificationResult,
    )

    calls = []

    class Executor:
        async def execute(self, request):
            calls.append(request)

            if len(calls) == 1:
                raise sandbox_process.WorkerPhaseBudgetReachedError("initial phase limit")

            return sandbox_process.WorkerExecutionResult(
                summary="repaired",
            )

    hygiene = AsyncMock()

    verifier = AsyncMock(
        side_effect=[
            WorkerSelfVerificationResult(
                command=("python", "-m", "pytest", "-q"),
                exit_code=0,
                output="693 passed",
            ),
            WorkerSelfVerificationResult(
                command=("python", "-m", "pytest", "-q"),
                exit_code=0,
                output="693 passed",
            ),
        ]
    )

    monkeypatch.setattr(
        sandbox_process,
        "apply_workspace_hygiene",
        hygiene,
    )
    monkeypatch.setattr(
        sandbox_process,
        "run_worker_self_verification",
        verifier,
    )

    result = await sandbox_process._execute_with_bounded_self_repair(
        executor=Executor(),
        goal="Implement the requested change.",
        workspace=tmp_path,
    )

    assert result.summary == "repaired"
    assert len(calls) == 2
    assert "phase limit before completing" in calls[1].goal
    assert hygiene.await_count == 2
    assert verifier.await_count == 2


@pytest.mark.asyncio
async def test_worker_releases_runtime_before_post_repair_hygiene(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from agent_platform.worker.self_verification import (
        WorkerSelfVerificationResult,
    )

    events: list[str] = []

    class Executor:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, request):
            self.calls += 1
            events.append(f"execute-{self.calls}")

            raise sandbox_process.WorkerPhaseBudgetReachedError(f"phase-{self.calls}-limit")

    async def hygiene(workspace) -> None:
        events.append("hygiene")

    async def verify(workspace):
        events.append("verify")

        return WorkerSelfVerificationResult(
            command=("python", "-m", "pytest", "-q"),
            exit_code=0,
            output="tests passed",
        )

    async def release_runtime() -> None:
        events.append("release-runtime")

    monkeypatch.setattr(
        sandbox_process,
        "apply_workspace_hygiene",
        hygiene,
    )
    monkeypatch.setattr(
        sandbox_process,
        "run_worker_self_verification",
        verify,
    )

    result = await sandbox_process._execute_with_bounded_self_repair(
        executor=Executor(),
        goal="Implement the requested change.",
        workspace=tmp_path,
        release_runtime=release_runtime,
    )

    assert events == [
        "execute-1",
        "hygiene",
        "verify",
        "execute-2",
        "release-runtime",
        "hygiene",
        "verify",
    ]

    assert "reached its model-call limit" in result.summary


@pytest.mark.asyncio
async def test_hygiene_failure_becomes_repair_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from agent_platform.worker.self_verification import (
        WorkerSelfVerificationResult,
    )
    from agent_platform.worker.workspace_hygiene import (
        WorkspaceHygieneError,
    )

    calls = []

    class Executor:
        async def execute(self, request):
            calls.append(request)

            if len(calls) == 1:
                raise sandbox_process.WorkerPhaseBudgetReachedError("initial phase limit")

            return sandbox_process.WorkerExecutionResult(
                summary="repaired",
            )

    hygiene = AsyncMock(
        side_effect=[
            WorkspaceHygieneError("Worker workspace hygiene failed at ruff_format."),
            None,
        ]
    )

    verifier = AsyncMock(
        side_effect=[
            WorkerSelfVerificationResult(
                command=("python", "-m", "pytest", "-q"),
                exit_code=2,
                output="SyntaxError: invalid syntax",
            ),
            WorkerSelfVerificationResult(
                command=("python", "-m", "pytest", "-q"),
                exit_code=0,
                output="tests passed",
            ),
        ]
    )

    monkeypatch.setattr(
        sandbox_process,
        "apply_workspace_hygiene",
        hygiene,
    )
    monkeypatch.setattr(
        sandbox_process,
        "run_worker_self_verification",
        verifier,
    )

    result = await sandbox_process._execute_with_bounded_self_repair(
        executor=Executor(),
        goal="Implement the requested change.",
        workspace=tmp_path,
    )

    assert result.summary == "repaired"

    assert len(calls) == 2

    repair_goal = calls[1].goal

    assert "phase limit before completing" in repair_goal
    assert "SyntaxError: invalid syntax" in repair_goal
    assert "Workspace hygiene evidence" in repair_goal
    assert "ruff_format" in repair_goal

    assert hygiene.await_count == 2
    assert verifier.await_count == 2
