from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class WorkerWorkspaceError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerWorkspace:
    path: Path
    base_revision: str


class DisposableWorkerWorkspace:
    """Create a fresh disposable workspace for one Worker execution."""

    def __init__(
        self,
        *,
        repository_url: str,
        workspace_parent: Path,
        base_branch: str = "main",
    ) -> None:
        if not repository_url.strip():
            raise ValueError("repository_url must not be empty.")

        self._repository_url = repository_url
        self._workspace_parent = workspace_parent.resolve()
        self._base_branch = base_branch

    @contextmanager
    def open(
        self,
    ) -> Iterator[WorkerWorkspace]:
        self._workspace_parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        workspace_path = Path(
            tempfile.mkdtemp(
                prefix="worker-",
                dir=self._workspace_parent,
            )
        )

        try:
            self._clone(workspace_path)

            base_revision = self._git(
                workspace_path,
                "rev-parse",
                "HEAD",
            ).strip()

            yield WorkerWorkspace(
                path=workspace_path,
                base_revision=base_revision,
            )
        finally:
            shutil.rmtree(
                workspace_path,
                ignore_errors=True,
            )

    def _clone(
        self,
        workspace_path: Path,
    ) -> None:
        result = subprocess.run(
            [
                "git",
                "clone",
                "--branch",
                self._base_branch,
                "--single-branch",
                "--no-tags",
                self._repository_url,
                str(workspace_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise WorkerWorkspaceError(self._format_git_error(result))

    @staticmethod
    def _git(
        repo: Path,
        *args: str,
    ) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise WorkerWorkspaceError(DisposableWorkerWorkspace._format_git_error(result))

        return result.stdout

    @staticmethod
    def _format_git_error(
        result: subprocess.CompletedProcess[str],
    ) -> str:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Git error"

        return f"Git command failed: {detail}"
