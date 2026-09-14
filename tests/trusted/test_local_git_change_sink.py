import subprocess
from pathlib import Path

import pytest

from agent_platform.adapters.git.local import (
    LocalGitChangeSink,
    LocalGitError,
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
def git_repo(
    tmp_path: Path,
) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()

    git(repo, "init", "-b", "main")

    (repo / "README.md").write_text(
        "# test\n",
        encoding="utf-8",
    )

    git(repo, "add", "README.md")
    git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "initial",
    )

    base_revision = git(
        repo,
        "rev-parse",
        "HEAD",
    )

    return repo, base_revision


@pytest.mark.asyncio
async def test_allowed_change_creates_branch_and_commit(
    git_repo: tuple[Path, str],
) -> None:
    repo, base_revision = git_repo

    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=LocalGitChangeSink(repo),
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

    assert result.reference.startswith("git:")
    assert git(repo, "branch", "--show-current") == "agent/add-example"

    assert (repo / "src/example.py").read_text(encoding="utf-8") == "VALUE = 42\n"

    assert (
        git(
            repo,
            "log",
            "-1",
            "--pretty=%s",
        )
        == "feat: add example"
    )


@pytest.mark.asyncio
async def test_protected_change_does_not_mutate_repository(
    git_repo: tuple[Path, str],
) -> None:
    repo, base_revision = git_repo

    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=LocalGitChangeSink(repo),
    )

    change_set = ChangeSet(
        base_revision=base_revision,
        branch_name="agent/attack-gates",
        commit_message="chore: weaken gates",
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

    assert git(repo, "branch", "--show-current") == "main"
    assert git(repo, "rev-parse", "HEAD") == base_revision
    assert not (repo / ".github").exists()


@pytest.mark.asyncio
async def test_sink_rejects_dirty_workspace(
    git_repo: tuple[Path, str],
) -> None:
    repo, base_revision = git_repo

    (repo / "dirty.txt").write_text(
        "dirty\n",
        encoding="utf-8",
    )

    sink = LocalGitChangeSink(repo)

    change_set = ChangeSet(
        base_revision=base_revision,
        branch_name="agent/example",
        commit_message="feat: example",
        changes=(
            FileChange(
                path="src/example.py",
                operation=FileChangeOperation.UPSERT,
                content="x = 1\n",
            ),
        ),
    )

    with pytest.raises(
        LocalGitError,
        match="workspace must be clean",
    ):
        await sink.publish(change_set)

    assert git(repo, "branch", "--show-current") == "main"


@pytest.mark.asyncio
async def test_sink_rejects_wrong_base_revision(
    git_repo: tuple[Path, str],
) -> None:
    repo, _ = git_repo

    sink = LocalGitChangeSink(repo)

    change_set = ChangeSet(
        base_revision="0" * 40,
        branch_name="agent/example",
        commit_message="feat: example",
        changes=(
            FileChange(
                path="src/example.py",
                operation=FileChangeOperation.UPSERT,
                content="x = 1\n",
            ),
        ),
    )

    with pytest.raises(
        LocalGitError,
        match="base_revision",
    ):
        await sink.publish(change_set)

    assert git(repo, "branch", "--show-current") == "main"


@pytest.mark.asyncio
async def test_sink_prevents_path_escape(
    git_repo: tuple[Path, str],
) -> None:
    repo, base_revision = git_repo

    sink = LocalGitChangeSink(repo)

    change_set = ChangeSet(
        base_revision=base_revision,
        branch_name="agent/path-escape",
        commit_message="feat: escape",
        changes=(
            FileChange(
                path="../outside.txt",
                operation=FileChangeOperation.UPSERT,
                content="escape\n",
            ),
        ),
    )

    with pytest.raises(
        LocalGitError,
        match="escapes repository root",
    ):
        await sink.publish(change_set)

    assert not (repo.parent / "outside.txt").exists()
