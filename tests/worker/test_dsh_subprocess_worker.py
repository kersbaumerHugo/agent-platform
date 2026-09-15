import os
import sys
from pathlib import Path

import pytest

from agent_platform.adapters.workers import (
    dsh_subprocess,
)
from agent_platform.adapters.workers.dsh_subprocess import (
    DshSubprocessWorkerExecutor,
)
from agent_platform.worker.session import (
    WorkerExecutionRequest,
    WorkerExecutionResult,
)


@pytest.mark.asyncio
async def test_dsh_subprocess_worker_builds_isolated_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeSupervisor:
        def __init__(
            self,
            **kwargs: object,
        ) -> None:
            captured.update(kwargs)

        async def execute(
            self,
            request: WorkerExecutionRequest,
        ) -> WorkerExecutionResult:
            captured["request"] = request

            return WorkerExecutionResult(summary="completed")

    monkeypatch.setattr(
        dsh_subprocess,
        "SubprocessWorkerExecutor",
        FakeSupervisor,
    )

    monkeypatch.setenv(
        "OPENROUTER_API_KEY",
        "must-not-leak",
    )

    worker = DshSubprocessWorkerExecutor(
        dsh_home=tmp_path / "dsh",
        provider="deepseek-official",
        model="test-model",
        env={
            "PATH": os.environ["PATH"],
            "DEEPSEEK_BASE_URL": ("http://model-gateway/internal/v1"),
            "DEEPSEEK_API_KEY": "internal-key",
        },
        request_timeout_seconds=120.0,
        hard_timeout_seconds=300.0,
        terminate_grace_seconds=5.0,
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = await worker.execute(
        WorkerExecutionRequest(
            goal="Implement the task.",
            workspace=workspace,
        )
    )

    assert result.summary == "completed"

    command_factory = captured["command_factory"]

    command = command_factory(workspace)

    assert command == (
        sys.executable,
        "-m",
        "agent_platform.worker.dsh_process",
    )

    process_env = captured["env"]

    assert process_env["DEEPSEEK_API_KEY"] == ("internal-key")

    assert process_env["AGENT_PLATFORM_DSH_MODEL"] == "test-model"

    assert process_env["AGENT_PLATFORM_DSH_PROVIDER"] == "deepseek-official"

    assert "OPENROUTER_API_KEY" not in process_env


def test_dsh_subprocess_worker_requires_explicit_path(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="include PATH",
    ):
        DshSubprocessWorkerExecutor(
            dsh_home=tmp_path / "dsh",
            provider="deepseek-official",
            model="test-model",
            env={},
        )


def test_dsh_subprocess_worker_rejects_invalid_request_timeout(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="request_timeout_seconds",
    ):
        DshSubprocessWorkerExecutor(
            dsh_home=tmp_path / "dsh",
            provider="deepseek-official",
            model="test-model",
            env={"PATH": os.environ["PATH"]},
            request_timeout_seconds=0,
        )
