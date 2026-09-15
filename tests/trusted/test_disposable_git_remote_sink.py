import subprocess
from pathlib import Path

import pytest

from agent_platform.adapters.git.disposable import (
    DisposableGitRemoteChangeSink,
)
from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
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


@pytest.mark.asyncio
async def test_publication_uses_and_removes_disposable_workspace(
    tmp_path: Path,
) -> None:
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

    git(seed, "add", "README.md")

    git(
        seed,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "initial",
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

    base_revision = git(
        seed,
        "rev-parse",
        "HEAD",
    )

    workspaces = tmp_path / "workspaces"

    sink = DisposableGitRemoteChangeSink(
        repository_url=str(remote),
        workspace_parent=workspaces,
    )

    result = await sink.publish(
        ChangeSet(
            base_revision=base_revision,
            branch_name="agent/disposable-test",
            commit_message="docs: disposable test",
            changes=(
                FileChange(
                    path="docs/example.md",
                    operation=FileChangeOperation.UPSERT,
                    content="hello\n",
                ),
            ),
        )
    )

    assert result.reference.startswith("git-remote:origin/agent/disposable-test@")

    remote_branch = subprocess.run(
        [
            "git",
            "--git-dir",
            str(remote),
            "rev-parse",
            "refs/heads/agent/disposable-test",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert remote_branch != base_revision

    assert list(workspaces.iterdir()) == []


@pytest.mark.asyncio
async def test_workspace_is_removed_when_base_revision_is_wrong(
    tmp_path: Path,
) -> None:
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

    git(seed, "add", "README.md")
    git(
        seed,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "initial",
    )

    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "main")

    workspaces = tmp_path / "workspaces"

    sink = DisposableGitRemoteChangeSink(
        repository_url=str(remote),
        workspace_parent=workspaces,
    )

    with pytest.raises(
        Exception,
        match="does not match ChangeSet base_revision",
    ):
        await sink.publish(
            ChangeSet(
                base_revision="0" * 40,
                branch_name="agent/wrong-base",
                commit_message="docs: wrong base",
                changes=(
                    FileChange(
                        path="docs/example.md",
                        operation=FileChangeOperation.UPSERT,
                        content="hello\n",
                    ),
                ),
            )
        )

    assert list(workspaces.iterdir()) == []


@pytest.mark.asyncio
async def test_workspace_is_removed_when_remote_branch_exists(
    tmp_path: Path,
) -> None:
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

    git(seed, "add", "README.md")
    git(
        seed,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "initial",
    )

    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "main")

    base_revision = git(
        seed,
        "rev-parse",
        "HEAD",
    )

    git(
        seed,
        "branch",
        "agent/existing",
    )

    git(
        seed,
        "push",
        "origin",
        "agent/existing",
    )

    workspaces = tmp_path / "workspaces"

    sink = DisposableGitRemoteChangeSink(
        repository_url=str(remote),
        workspace_parent=workspaces,
    )

    with pytest.raises(
        Exception,
        match="Remote branch already exists",
    ):
        await sink.publish(
            ChangeSet(
                base_revision=base_revision,
                branch_name="agent/existing",
                commit_message="docs: duplicate branch",
                changes=(
                    FileChange(
                        path="docs/example.md",
                        operation=FileChangeOperation.UPSERT,
                        content="hello\n",
                    ),
                ),
            )
        )

    assert list(workspaces.iterdir()) == []
