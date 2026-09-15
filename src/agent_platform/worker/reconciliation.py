from __future__ import annotations

import shutil
from pathlib import Path


class WorkerWorkspaceReconciler:
    """Remove disposable Worker workspaces left by interrupted processes.

    V0 invariant: reconciliation runs at supervisor startup, before new Worker
    executions are accepted from this workspace parent.
    """

    def __init__(
        self,
        *,
        workspace_parent: Path,
    ) -> None:
        self._workspace_parent = workspace_parent.resolve()

    def reconcile(
        self,
    ) -> tuple[str, ...]:
        if not self._workspace_parent.exists():
            return ()

        removed: list[str] = []

        for candidate in sorted(
            self._workspace_parent.iterdir(),
            key=lambda path: path.name,
        ):
            if not candidate.name.startswith("worker-"):
                continue

            # Never follow a symlink during cleanup.
            if candidate.is_symlink():
                continue

            if not candidate.is_dir():
                continue

            shutil.rmtree(candidate)
            removed.append(candidate.name)

        return tuple(removed)
