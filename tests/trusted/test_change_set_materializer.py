from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_platform.trust.change_set_identity import identify_change_set
from agent_platform.trust.change_set_materializer import (
    ChangeSetMaterializationError,
    DisposableChangeSetMaterializer,
)
from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _trusted_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "trusted"
    repo.mkdir()

    _git(repo, "init")
    (repo / "existing.txt").write_text("before\n", encoding="utf-8")
    (repo / "delete-me.txt").write_text("delete\n", encoding="utf-8")

    _git(repo, "add", "existing.txt", "delete-me.txt")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "baseline",
    )

    return repo, _git(repo, "rev-parse", "HEAD")


def _change_set(base_revision: str) -> ChangeSet:
    return ChangeSet(
        base_revision=base_revision,
        branch_name="coding/task-123",
        commit_message="chore: supervised change",
        changes=(
            FileChange(
                path="existing.txt",
                operation=FileChangeOperation.UPSERT,
                content="after\n",
            ),
            FileChange(
                path="new.txt",
                operation=FileChangeOperation.UPSERT,
                content="new\n",
            ),
            FileChange(
                path="delete-me.txt",
                operation=FileChangeOperation.DELETE,
            ),
        ),
    )


def test_materializes_exact_change_set_from_trusted_base(tmp_path: Path) -> None:
    repo, revision = _trusted_repo(tmp_path)
    change_set = _change_set(revision)
    materializer = DisposableChangeSetMaterializer(
        trusted_repo_root=repo,
        workspace_parent=tmp_path / "workspaces",
    )

    with materializer.materialize(change_set) as materialized:
        assert materialized.base_revision == revision
        assert materialized.identity == identify_change_set(change_set)
        assert (materialized.workspace / "existing.txt").read_text(encoding="utf-8") == "after\n"
        assert (materialized.workspace / "new.txt").read_text(encoding="utf-8") == "new\n"
        assert not (materialized.workspace / "delete-me.txt").exists()
        assert _git(materialized.workspace, "remote") == ""

    assert (repo / "existing.txt").read_text(encoding="utf-8") == "before\n"
    assert (repo / "delete-me.txt").exists()


def test_materialized_workspace_is_deleted_after_context(tmp_path: Path) -> None:
    repo, revision = _trusted_repo(tmp_path)
    materializer = DisposableChangeSetMaterializer(
        trusted_repo_root=repo,
        workspace_parent=tmp_path / "workspaces",
    )

    with materializer.materialize(_change_set(revision)) as materialized:
        workspace = materialized.workspace
        assert workspace.exists()

    assert not workspace.exists()


def test_rejects_stale_or_untrusted_base_revision(tmp_path: Path) -> None:
    repo, _ = _trusted_repo(tmp_path)
    materializer = DisposableChangeSetMaterializer(
        trusted_repo_root=repo,
        workspace_parent=tmp_path / "workspaces",
    )

    change_set = _change_set("b" * 40)

    with pytest.raises(
        ChangeSetMaterializationError,
        match="trusted repository HEAD",
    ):
        with materializer.materialize(change_set):
            pass


@pytest.mark.parametrize(
    "path",
    (
        "../escape.txt",
        "/absolute.txt",
        "./noncanonical.txt",
        ".git/config",
    ),
)
def test_rejects_unsafe_change_paths(
    tmp_path: Path,
    path: str,
) -> None:
    repo, revision = _trusted_repo(tmp_path)
    materializer = DisposableChangeSetMaterializer(
        trusted_repo_root=repo,
        workspace_parent=tmp_path / "workspaces",
    )
    change_set = ChangeSet(
        base_revision=revision,
        branch_name="coding/task-123",
        commit_message="chore: unsafe",
        changes=(
            FileChange(
                path=path,
                operation=FileChangeOperation.UPSERT,
                content="unsafe\n",
            ),
        ),
    )

    with pytest.raises(ChangeSetMaterializationError):
        with materializer.materialize(change_set):
            pass


def test_rejects_noop_change_set_materialization(tmp_path: Path) -> None:
    repo, revision = _trusted_repo(tmp_path)
    materializer = DisposableChangeSetMaterializer(
        trusted_repo_root=repo,
        workspace_parent=tmp_path / "workspaces",
    )
    change_set = ChangeSet(
        base_revision=revision,
        branch_name="coding/task-123",
        commit_message="chore: noop",
        changes=(
            FileChange(
                path="existing.txt",
                operation=FileChangeOperation.UPSERT,
                content="before\n",
            ),
        ),
    )

    with pytest.raises(
        ChangeSetMaterializationError,
        match="do not match ChangeSet paths",
    ):
        with materializer.materialize(change_set):
            pass


def test_rejects_delete_of_missing_file(tmp_path: Path) -> None:
    repo, revision = _trusted_repo(tmp_path)
    materializer = DisposableChangeSetMaterializer(
        trusted_repo_root=repo,
        workspace_parent=tmp_path / "workspaces",
    )
    change_set = ChangeSet(
        base_revision=revision,
        branch_name="coding/task-123",
        commit_message="chore: invalid delete",
        changes=(
            FileChange(
                path="missing.txt",
                operation=FileChangeOperation.DELETE,
            ),
        ),
    )

    with pytest.raises(
        ChangeSetMaterializationError,
        match="Cannot delete missing file",
    ):
        with materializer.materialize(change_set):
            pass


def test_assert_exact_detects_content_drift_after_materialization(
    tmp_path: Path,
) -> None:
    repo, revision = _trusted_repo(tmp_path)
    change_set = _change_set(revision)
    materializer = DisposableChangeSetMaterializer(
        trusted_repo_root=repo,
        workspace_parent=tmp_path / "workspaces",
    )

    with materializer.materialize(change_set) as materialized:
        (materialized.workspace / "existing.txt").write_text(
            "tampered\n",
            encoding="utf-8",
        )

        with pytest.raises(
            ChangeSetMaterializationError,
            match="identity",
        ):
            materializer.assert_exact(
                materialized=materialized,
                change_set=change_set,
            )


def test_assert_exact_detects_head_drift_after_materialization(
    tmp_path: Path,
) -> None:
    repo, revision = _trusted_repo(tmp_path)
    change_set = _change_set(revision)
    materializer = DisposableChangeSetMaterializer(
        trusted_repo_root=repo,
        workspace_parent=tmp_path / "workspaces",
    )

    with materializer.materialize(change_set) as materialized:
        _git(materialized.workspace, "add", "-A")
        _git(
            materialized.workspace,
            "-c",
            "user.name=Verifier",
            "-c",
            "user.email=verifier@example.invalid",
            "commit",
            "-m",
            "unexpected verifier mutation",
        )

        with pytest.raises(
            ChangeSetMaterializationError,
            match="HEAD changed",
        ):
            materializer.assert_exact(
                materialized=materialized,
                change_set=change_set,
            )
