import subprocess
from pathlib import Path

import pytest

from agent_platform.trust.publisher import ChangeSet
from agent_platform.worker import runtime as worker_runtime
from agent_platform.worker.publication import (
    TrustedPublicationResponse,
)
from agent_platform.worker.session import (
    WorkerDevelopmentTask,
    WorkerExecutionRequest,
    WorkerExecutionResult,
)


def git(
    repo: Path,
    *args: str,
) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    return result.stdout.strip()


@pytest.fixture
def remote_repo(
    tmp_path: Path,
) -> Path:
    remote = tmp_path / "remote.git"

    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
        text=True,
    )

    seed = tmp_path / "seed"
    seed.mkdir()

    git(seed, "init", "-b", "main")

    (seed / "README.md").write_text(
        "# baseline\n",
        encoding="utf-8",
    )

    git(seed, "add", ".")

    git(
        seed,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "baseline",
    )

    git(
        seed,
        "remote",
        "add",
        "origin",
        str(remote),
    )

    git(
        seed,
        "push",
        "-u",
        "origin",
        "main",
    )

    return remote


@pytest.mark.asyncio
async def test_runtime_reconciles_and_uses_supervised_worker(
    tmp_path: Path,
    remote_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeSubprocessWorker:
        def __init__(
            self,
            **kwargs: object,
        ) -> None:
            captured["executor_kwargs"] = kwargs

        async def execute(
            self,
            request: WorkerExecutionRequest,
        ) -> WorkerExecutionResult:
            captured["workspace"] = request.workspace

            (request.workspace / "generated.txt").write_text(
                "generated\n",
                encoding="utf-8",
            )

            return WorkerExecutionResult(summary="implemented")

    class FakePublisher:
        def __init__(
            self,
            *,
            socket_path: Path,
        ) -> None:
            captured["socket_path"] = socket_path

        async def publish(
            self,
            change_set: ChangeSet,
        ) -> TrustedPublicationResponse:
            captured["change_set"] = change_set

            return TrustedPublicationResponse(
                status="accepted",
                reference="test://proposal",
            )

    monkeypatch.setattr(
        worker_runtime,
        "DshSubprocessWorkerExecutor",
        FakeSubprocessWorker,
    )

    monkeypatch.setattr(
        worker_runtime,
        "TrustedPublicationClient",
        FakePublisher,
    )

    parent = tmp_path / "workspaces"
    parent.mkdir()

    orphan = parent / "worker-orphan"
    orphan.mkdir()

    (orphan / "partial.txt").write_text(
        "partial\n",
        encoding="utf-8",
    )

    runtime = worker_runtime.build_supervised_worker_runtime(
        repository_url=str(remote_repo),
        workspace_parent=parent,
        publisher_socket_path=(tmp_path / "trusted.sock"),
        dsh_home=tmp_path / "dsh",
        provider="deepseek-official",
        model="test-model",
        env={"PATH": "/usr/bin:/bin"},
        hard_timeout_seconds=30.0,
    )

    assert runtime.reconciled_workspaces == ("worker-orphan",)

    assert not orphan.exists()

    result = await runtime.run(
        WorkerDevelopmentTask(
            goal="Create generated.txt.",
            branch_name="agent/runtime-test",
            commit_message="test: runtime wiring",
        )
    )

    assert result.publication.status == "accepted"
    assert result.publication.reference == ("test://proposal")

    assert result.change_set.changed_paths == ("generated.txt",)

    change_set = captured["change_set"]

    assert isinstance(change_set, ChangeSet)
    assert change_set.changed_paths == ("generated.txt",)

    executor_kwargs = captured["executor_kwargs"]

    assert isinstance(executor_kwargs, dict)

    assert executor_kwargs["hard_timeout_seconds"] == 30.0

    assert list(parent.iterdir()) == []
