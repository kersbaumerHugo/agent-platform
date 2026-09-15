from pathlib import Path

from agent_platform.worker.reconciliation import (
    WorkerWorkspaceReconciler,
)


def test_reconciler_removes_orphan_worker_directories(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "workspaces"
    parent.mkdir()

    first = parent / "worker-orphan-a"
    second = parent / "worker-orphan-b"

    first.mkdir()
    second.mkdir()

    (first / "partial.txt").write_text(
        "partial\n",
        encoding="utf-8",
    )

    nested = second / "nested"
    nested.mkdir()

    (nested / "state.txt").write_text(
        "state\n",
        encoding="utf-8",
    )

    removed = WorkerWorkspaceReconciler(
        workspace_parent=parent,
    ).reconcile()

    assert removed == (
        "worker-orphan-a",
        "worker-orphan-b",
    )

    assert list(parent.iterdir()) == []


def test_reconciler_preserves_unrelated_paths(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "workspaces"
    parent.mkdir()

    unrelated = parent / "keep-me"
    unrelated.mkdir()

    worker_file = parent / "worker-not-a-directory"
    worker_file.write_text(
        "keep\n",
        encoding="utf-8",
    )

    outside = tmp_path / "outside"
    outside.mkdir()

    symlink = parent / "worker-symlink"
    symlink.symlink_to(
        outside,
        target_is_directory=True,
    )

    removed = WorkerWorkspaceReconciler(
        workspace_parent=parent,
    ).reconcile()

    assert removed == ()

    assert unrelated.is_dir()
    assert worker_file.is_file()
    assert symlink.is_symlink()
    assert outside.is_dir()


def test_reconciler_accepts_missing_parent(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "missing"

    removed = WorkerWorkspaceReconciler(
        workspace_parent=parent,
    ).reconcile()

    assert removed == ()
