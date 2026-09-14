import subprocess
from pathlib import Path

import pytest

from agent_platform.adapters.git.remote import (
    GitRemoteChangeSink,
    GitRemoteError,
)
from agent_platform.trust.change_policy import ChangePolicy
from agent_platform.trust.publisher import (
    ChangeRejectedError,
    ChangeSet,
    FileChange,
    FileChangeOperation,
    TrustedPublisher,
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
def remote_git_repo(
    tmp_path: Path,
) -> tuple[Path, Path, str]:
    remote = tmp_path / "remote.git"

    subprocess.run(
        [
            "git",
            "init",
            "--bare",
            "--initial-branch=main",
            str(remote),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    seed = tmp_path / "seed"
    seed.mkdir()

    git(seed, "init", "-b", "main")

    (seed / "README.md").write_text(
        "# test\n",
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

    workspace = tmp_path / "workspace"

    subprocess.run(
        [
            "git",
            "clone",
            str(remote),
            str(workspace),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    base_revision = git(
        workspace,
        "rev-parse",
        "HEAD",
    )

    return workspace, remote, base_revision


@pytest.mark.asyncio
async def test_allowed_change_pushes_new_remote_branch(
    remote_git_repo: tuple[Path, Path, str],
) -> None:
    workspace, remote, base_revision = remote_git_repo

    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=GitRemoteChangeSink(workspace),
    )

    change_set = ChangeSet(
        base_revision=base_revision,
        branch_name="agent/add-example",
        commit_message="feat: add example",
        changes=(
            FileChange(
                path="src/example.py",
                operation=FileChangeOperation.UPSERT,
                content="VALUE = 42\n",
            ),
        ),
    )

    result = await publisher.publish(change_set)

    assert result.reference.startswith("git-remote:origin/agent/add-example@")

    remote_commit = git(
        remote,
        "rev-parse",
        "refs/heads/agent/add-example",
    )

    assert remote_commit != base_revision

    assert (
        git(
            remote,
            "show",
            "refs/heads/agent/add-example:src/example.py",
        )
        == "VALUE = 42"
    )

    assert (
        git(
            remote,
            "rev-parse",
            "refs/heads/main",
        )
        == base_revision
    )


@pytest.mark.asyncio
async def test_protected_change_never_reaches_remote(
    remote_git_repo: tuple[Path, Path, str],
) -> None:
    workspace, remote, base_revision = remote_git_repo

    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=GitRemoteChangeSink(workspace),
    )

    change_set = ChangeSet(
        base_revision=base_revision,
        branch_name="agent/weaken-ci",
        commit_message="chore: weaken ci",
        changes=(
            FileChange(
                path=".github/workflows/ci.yml",
                operation=FileChangeOperation.UPSERT,
                content="name: bypass\n",
            ),
        ),
    )

    with pytest.raises(ChangeRejectedError):
        await publisher.publish(change_set)

    result = subprocess.run(
        [
            "git",
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/agent/weaken-ci",
        ],
        cwd=remote,
        check=False,
    )

    assert result.returncode != 0
    assert git(workspace, "branch", "--show-current") == "main"
    assert git(workspace, "rev-parse", "HEAD") == base_revision


@pytest.mark.asyncio
async def test_existing_remote_branch_is_not_modified(
    remote_git_repo: tuple[Path, Path, str],
) -> None:
    workspace, remote, base_revision = remote_git_repo

    git(
        workspace,
        "push",
        "origin",
        f"{base_revision}:refs/heads/agent/existing",
    )

    existing_revision = git(
        remote,
        "rev-parse",
        "refs/heads/agent/existing",
    )

    sink = GitRemoteChangeSink(workspace)

    change_set = ChangeSet(
        base_revision=base_revision,
        branch_name="agent/existing",
        commit_message="feat: overwrite existing",
        changes=(
            FileChange(
                path="src/example.py",
                operation=FileChangeOperation.UPSERT,
                content="VALUE = 99\n",
            ),
        ),
    )

    with pytest.raises(
        GitRemoteError,
        match="Remote branch already exists",
    ):
        await sink.publish(change_set)

    assert (
        git(
            remote,
            "rev-parse",
            "refs/heads/agent/existing",
        )
        == existing_revision
    )

    assert git(workspace, "branch", "--show-current") == "main"


@pytest.mark.asyncio
async def test_missing_remote_fails_before_local_mutation(
    remote_git_repo: tuple[Path, Path, str],
) -> None:
    workspace, _, base_revision = remote_git_repo

    sink = GitRemoteChangeSink(
        workspace,
        remote_name="missing",
    )

    change_set = ChangeSet(
        base_revision=base_revision,
        branch_name="agent/example",
        commit_message="feat: example",
        changes=(
            FileChange(
                path="src/example.py",
                operation=FileChangeOperation.UPSERT,
                content="VALUE = 42\n",
            ),
        ),
    )

    with pytest.raises(
        GitRemoteError,
        match="remote is not configured",
    ):
        await sink.publish(change_set)

    assert git(workspace, "branch", "--show-current") == "main"
    assert git(workspace, "rev-parse", "HEAD") == base_revision


@pytest.mark.asyncio
async def test_rejects_change_based_on_unpublished_local_revision(
    tmp_path: Path,
) -> None:
    import subprocess

    from agent_platform.adapters.git.remote import (
        GitRemoteChangeSink,
        GitRemoteError,
    )
    from agent_platform.trust.publisher import (
        ChangeSet,
        FileChange,
        FileChangeOperation,
    )

    def run_git(
        cwd: Path,
        *args: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=check,
            capture_output=True,
            text=True,
        )

    remote = tmp_path / "remote.git"

    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
        text=True,
    )

    repo = tmp_path / "repo"
    repo.mkdir()

    run_git(repo, "init", "-b", "main")

    (repo / "README.md").write_text(
        "# baseline\n",
        encoding="utf-8",
    )

    run_git(repo, "add", "README.md")
    run_git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "initial",
    )

    run_git(
        repo,
        "remote",
        "add",
        "origin",
        str(remote),
    )

    run_git(
        repo,
        "push",
        "-u",
        "origin",
        "main",
    )

    remote_main = run_git(
        repo,
        "rev-parse",
        "HEAD",
    ).stdout.strip()

    run_git(
        repo,
        "switch",
        "-c",
        "trusted/unpublished",
    )

    (repo / "trusted.txt").write_text(
        "local-only trusted change\n",
        encoding="utf-8",
    )

    run_git(repo, "add", "trusted.txt")
    run_git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "trusted local commit",
    )

    local_revision = run_git(
        repo,
        "rev-parse",
        "HEAD",
    ).stdout.strip()

    assert local_revision != remote_main

    sink = GitRemoteChangeSink(
        repo,
        remote_name="origin",
        base_branch="main",
    )

    change_set = ChangeSet(
        base_revision=local_revision,
        branch_name="agent/attempt-inherited-change",
        commit_message="docs: innocent looking change",
        changes=(
            FileChange(
                path="docs/example.md",
                operation=FileChangeOperation.UPSERT,
                content="hello\n",
            ),
        ),
    )

    with pytest.raises(
        GitRemoteError,
        match="does not match remote base branch",
    ):
        await sink.publish(change_set)

    remote_branch = run_git(
        repo,
        "ls-remote",
        "--heads",
        "origin",
        "refs/heads/agent/attempt-inherited-change",
    )

    assert remote_branch.stdout.strip() == ""

    current_revision = run_git(
        repo,
        "rev-parse",
        "HEAD",
    ).stdout.strip()

    assert current_revision == local_revision
