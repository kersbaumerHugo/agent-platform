import subprocess
import sys
from pathlib import Path

import pytest

from agent_platform.worker.session import (
    WorkerDevelopmentSession,
    WorkerDevelopmentTask,
)
from agent_platform.worker.supervisor import (
    SubprocessWorkerExecutor,
    WorkerProcessTimeoutError,
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
async def test_hard_timeout_cleans_worker_workspace(
    tmp_path: Path,
    remote_repo: Path,
) -> None:
    parent = tmp_path / "workspaces"

    def command_factory(
        workspace: Path,
    ) -> tuple[str, ...]:
        return (
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "import time; "
                "Path('partial.txt').write_text("
                "'partial\\n', encoding='utf-8'); "
                "time.sleep(60)"
            ),
        )

    session = WorkerDevelopmentSession(
        workspace=DisposableWorkerWorkspace(
            repository_url=str(remote_repo),
            workspace_parent=parent,
        ),
        executor=SubprocessWorkerExecutor(
            command_factory=command_factory,
            timeout_seconds=0.2,
            terminate_grace_seconds=0.2,
        ),
    )

    with pytest.raises(
        WorkerProcessTimeoutError,
        match="hard timeout",
    ):
        await session.run(
            WorkerDevelopmentTask(
                goal="Hang forever.",
                branch_name="agent/timeout-test",
                commit_message="test: timeout",
            )
        )

    assert list(parent.iterdir()) == []
