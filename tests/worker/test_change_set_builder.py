import subprocess
from pathlib import Path

import pytest

from agent_platform.trust.publisher import (
    FileChangeOperation,
)
from agent_platform.worker.change_set import (
    ChangeSetBuilder,
    ChangeSetBuildError,
    WorkspaceContainsNoChangesError,
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
def repo(
    tmp_path: Path,
) -> tuple[Path, str]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    git(workspace, "init", "-b", "main")

    (workspace / "modify.txt").write_text(
        "before\n",
        encoding="utf-8",
    )

    (workspace / "delete.txt").write_text(
        "delete me\n",
        encoding="utf-8",
    )

    git(workspace, "add", ".")

    git(
        workspace,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "baseline",
    )

    revision = git(
        workspace,
        "rev-parse",
        "HEAD",
    )

    return workspace, revision


def test_builds_changes_for_create_modify_delete(
    repo: tuple[Path, str],
) -> None:
    workspace, revision = repo

    (workspace / "modify.txt").write_text(
        "after\n",
        encoding="utf-8",
    )

    (workspace / "delete.txt").unlink()

    (workspace / "created.txt").write_text(
        "created\n",
        encoding="utf-8",
    )

    change_set = ChangeSetBuilder(workspace).build(
        branch_name="agent/change-set-test",
        commit_message="feat: change set test",
    )

    assert change_set.base_revision == revision
    assert change_set.branch_name == "agent/change-set-test"
    assert change_set.commit_message == "feat: change set test"

    assert change_set.changed_paths == (
        "created.txt",
        "delete.txt",
        "modify.txt",
    )

    created, deleted, modified = change_set.changes

    assert created.operation is FileChangeOperation.UPSERT
    assert created.content == "created\n"

    assert deleted.operation is FileChangeOperation.DELETE
    assert deleted.content is None

    assert modified.operation is FileChangeOperation.UPSERT
    assert modified.content == "after\n"


def test_build_is_deterministic(
    repo: tuple[Path, str],
) -> None:
    workspace, _ = repo

    (workspace / "z.txt").write_text(
        "z\n",
        encoding="utf-8",
    )

    (workspace / "a.txt").write_text(
        "a\n",
        encoding="utf-8",
    )

    builder = ChangeSetBuilder(workspace)

    first = builder.build(
        branch_name="agent/deterministic",
        commit_message="test: deterministic",
    )

    second = builder.build(
        branch_name="agent/deterministic",
        commit_message="test: deterministic",
    )

    assert first == second

    assert first.changed_paths == (
        "a.txt",
        "z.txt",
    )


def test_rejects_clean_workspace(
    repo: tuple[Path, str],
) -> None:
    workspace, _ = repo

    with pytest.raises(
        WorkspaceContainsNoChangesError,
        match="contains no changes",
    ):
        ChangeSetBuilder(workspace).build(
            branch_name="agent/empty",
            commit_message="test: empty",
        )


def test_rejects_binary_file(
    repo: tuple[Path, str],
) -> None:
    workspace, _ = repo

    (workspace / "binary.bin").write_bytes(b"\xff\xfe\x00\x01")

    with pytest.raises(
        ChangeSetBuildError,
        match="not UTF-8 text",
    ):
        ChangeSetBuilder(workspace).build(
            branch_name="agent/binary",
            commit_message="test: binary",
        )
