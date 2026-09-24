import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from agent_platform.trust.publisher import (
    FileChangeOperation,
)
from agent_platform.worker.session import (
    WorkerDevelopmentSession,
    WorkerDevelopmentTask,
    WorkerExecutionRequest,
    WorkerExecutionResult,
    WorkerNoChangesError,
)
from agent_platform.worker.workspace import (
    DisposableWorkerWorkspace,
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
) -> tuple[Path, str]:
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

    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "main")

    revision = git(seed, "rev-parse", "HEAD")

    return remote, revision


@dataclass
class FakeExecutor:
    async def execute(
        self,
        request: WorkerExecutionRequest,
    ) -> WorkerExecutionResult:
        assert request.goal == "Create worker output."

        (request.workspace / "worker-output.txt").write_text(
            "created by executor\n",
            encoding="utf-8",
        )

        return WorkerExecutionResult(summary="Created worker-output.txt.")


@dataclass
class FailingExecutor:
    async def execute(
        self,
        request: WorkerExecutionRequest,
    ) -> WorkerExecutionResult:
        (request.workspace / "partial.txt").write_text(
            "partial\n",
            encoding="utf-8",
        )

        raise RuntimeError("executor failed")


@dataclass
class NoChangeThenChangeExecutor:
    calls: int = 0
    first_execution_id: object | None = None
    retry_execution_id: object | None = None

    async def execute(
        self,
        request: WorkerExecutionRequest,
    ) -> WorkerExecutionResult:
        self.calls += 1

        if self.calls == 1:
            self.first_execution_id = request.execution_id
            return WorkerExecutionResult(summary="Let me inspect the repository first.")

        self.retry_execution_id = request.execution_id

        assert "final bounded implementation retry" in request.goal

        (request.workspace / "retry-output.txt").write_text(
            "created on retry\n",
            encoding="utf-8",
        )

        return WorkerExecutionResult(summary="Created retry-output.txt.")


@dataclass
class AlwaysNoChangeExecutor:
    calls: int = 0

    async def execute(
        self,
        request: WorkerExecutionRequest,
    ) -> WorkerExecutionResult:
        del request
        self.calls += 1

        return WorkerExecutionResult(summary=f"planning attempt {self.calls}")


@pytest.mark.asyncio
async def test_session_builds_change_set_and_cleans_workspace(
    tmp_path: Path,
    remote_repo: tuple[Path, str],
) -> None:
    remote, revision = remote_repo
    parent = tmp_path / "workspaces"

    session = WorkerDevelopmentSession(
        workspace=DisposableWorkerWorkspace(
            repository_url=str(remote),
            workspace_parent=parent,
        ),
        executor=FakeExecutor(),
    )

    change_set = await session.run(
        WorkerDevelopmentTask(
            goal="Create worker output.",
            branch_name="agent/session-test",
            commit_message="feat: session test",
        )
    )

    assert change_set.base_revision == revision
    assert change_set.changed_paths == ("worker-output.txt",)

    change = change_set.changes[0]

    assert change.operation is FileChangeOperation.UPSERT
    assert change.content == "created by executor\n"

    assert list(parent.iterdir()) == []


@pytest.mark.asyncio
async def test_session_cleans_workspace_when_executor_fails(
    tmp_path: Path,
    remote_repo: tuple[Path, str],
) -> None:
    remote, _ = remote_repo
    parent = tmp_path / "workspaces"

    session = WorkerDevelopmentSession(
        workspace=DisposableWorkerWorkspace(
            repository_url=str(remote),
            workspace_parent=parent,
        ),
        executor=FailingExecutor(),
    )

    with pytest.raises(
        RuntimeError,
        match="executor failed",
    ):
        await session.run(
            WorkerDevelopmentTask(
                goal="Fail.",
                branch_name="agent/failure",
                commit_message="test: failure",
            )
        )

    assert list(parent.iterdir()) == []


@pytest.mark.asyncio
async def test_session_retries_once_when_first_attempt_has_no_changes(
    tmp_path: Path,
    remote_repo: tuple[Path, str],
) -> None:
    remote, revision = remote_repo
    parent = tmp_path / "workspaces"
    executor = NoChangeThenChangeExecutor()

    session = WorkerDevelopmentSession(
        workspace=DisposableWorkerWorkspace(
            repository_url=str(remote),
            workspace_parent=parent,
        ),
        executor=executor,
    )

    change_set = await session.run(
        WorkerDevelopmentTask(
            goal="Create retry output.",
            branch_name="agent/retry-test",
            commit_message="test: retry worker",
        )
    )

    assert executor.calls == 2
    assert executor.first_execution_id is not None
    assert executor.retry_execution_id is not None
    assert executor.first_execution_id != executor.retry_execution_id

    assert change_set.base_revision == revision
    assert change_set.changed_paths == ("retry-output.txt",)
    assert change_set.changes[0].content == "created on retry\n"

    assert list(parent.iterdir()) == []


@pytest.mark.asyncio
async def test_session_fails_after_bounded_no_change_retry(
    tmp_path: Path,
    remote_repo: tuple[Path, str],
) -> None:
    remote, _ = remote_repo
    parent = tmp_path / "workspaces"
    executor = AlwaysNoChangeExecutor()

    session = WorkerDevelopmentSession(
        workspace=DisposableWorkerWorkspace(
            repository_url=str(remote),
            workspace_parent=parent,
        ),
        executor=executor,
    )

    with pytest.raises(WorkerNoChangesError) as exc_info:
        await session.run(
            WorkerDevelopmentTask(
                goal="Create something.",
                branch_name="agent/no-change",
                commit_message="test: no change",
            )
        )

    assert executor.calls == 2
    assert exc_info.value.first_summary == "planning attempt 1"
    assert exc_info.value.retry_summary == "planning attempt 2"
    assert "two attempts" in str(exc_info.value)

    assert list(parent.iterdir()) == []
