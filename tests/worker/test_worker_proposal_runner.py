import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agent_platform.trust.publisher import ChangeSet
from agent_platform.worker.proposal import (
    WorkerProposalRunner,
)
from agent_platform.worker.publication import (
    TrustedPublicationResponse,
)
from agent_platform.worker.session import (
    WorkerDevelopmentSession,
    WorkerDevelopmentTask,
    WorkerExecutionRequest,
    WorkerExecutionResult,
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

    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "main")

    return remote


@dataclass
class FakeExecutor:
    async def execute(
        self,
        request: WorkerExecutionRequest,
    ) -> WorkerExecutionResult:
        (request.workspace / "worker-output.txt").write_text(
            "created by worker\n",
            encoding="utf-8",
        )

        return WorkerExecutionResult(summary="Created worker-output.txt.")


@dataclass
class FakePublisher:
    published: list[ChangeSet] = field(default_factory=list)

    async def publish(
        self,
        change_set: ChangeSet,
    ) -> TrustedPublicationResponse:
        self.published.append(change_set)

        return TrustedPublicationResponse(
            status="accepted",
            reference=("https://github.com/kersbaumerHugo/agent-platform/pull/99"),
        )


@dataclass
class RejectingPublisher:
    published: list[ChangeSet] = field(default_factory=list)

    async def publish(
        self,
        change_set: ChangeSet,
    ) -> TrustedPublicationResponse:
        self.published.append(change_set)

        return TrustedPublicationResponse(
            status="rejected",
            reason_code="protected_path_modified",
            blocked_paths=(".github/workflows/ci.yml",),
        )


@pytest.mark.asyncio
async def test_runner_builds_and_submits_worker_proposal(
    tmp_path: Path,
    remote_repo: Path,
) -> None:
    workspace_parent = tmp_path / "workspaces"
    publisher = FakePublisher()

    runner = WorkerProposalRunner(
        session=WorkerDevelopmentSession(
            workspace=DisposableWorkerWorkspace(
                repository_url=str(remote_repo),
                workspace_parent=workspace_parent,
            ),
            executor=FakeExecutor(),
        ),
        publisher=publisher,
    )

    result = await runner.run(
        WorkerDevelopmentTask(
            goal="Create worker output.",
            branch_name="agent/proposal-test",
            commit_message="feat: proposal test",
        )
    )

    assert result.change_set.changed_paths == ("worker-output.txt",)

    assert len(publisher.published) == 1
    assert publisher.published[0] == result.change_set

    assert result.publication.status == "accepted"
    assert result.publication.reference is not None

    assert list(workspace_parent.iterdir()) == []


@pytest.mark.asyncio
async def test_runner_preserves_trusted_rejection(
    tmp_path: Path,
    remote_repo: Path,
) -> None:
    workspace_parent = tmp_path / "workspaces"
    publisher = RejectingPublisher()

    runner = WorkerProposalRunner(
        session=WorkerDevelopmentSession(
            workspace=DisposableWorkerWorkspace(
                repository_url=str(remote_repo),
                workspace_parent=workspace_parent,
            ),
            executor=FakeExecutor(),
        ),
        publisher=publisher,
    )

    result = await runner.run(
        WorkerDevelopmentTask(
            goal="Create worker output.",
            branch_name="agent/rejected-test",
            commit_message="feat: rejected test",
        )
    )

    assert result.publication.status == "rejected"

    assert result.publication.reason_code == "protected_path_modified"

    assert result.publication.blocked_paths == (".github/workflows/ci.yml",)

    assert list(workspace_parent.iterdir()) == []
