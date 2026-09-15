from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

from agent_platform.adapters.git.remote import GitRemoteChangeSink
from agent_platform.trust.publisher import (
    ChangeSet,
    PublicationResult,
)


class DisposableGitError(RuntimeError):
    pass


class DisposableGitRemoteChangeSink:
    """Publish each ChangeSet from a fresh, disposable Git workspace."""

    def __init__(
        self,
        repository_url: str,
        workspace_parent: Path,
        *,
        remote_name: str = "origin",
        base_branch: str = "main",
        author_name: str = "Agent Platform",
        author_email: str = "agent-platform@localhost",
    ) -> None:
        if not repository_url.strip():
            raise ValueError("repository_url must not be empty.")

        self._repository_url = repository_url
        self._workspace_parent = workspace_parent.resolve()
        self._remote_name = remote_name
        self._base_branch = base_branch
        self._author_name = author_name
        self._author_email = author_email

    async def publish(
        self,
        change_set: ChangeSet,
    ) -> PublicationResult:
        return await asyncio.to_thread(
            self._publish_sync,
            change_set,
        )

    def _publish_sync(
        self,
        change_set: ChangeSet,
    ) -> PublicationResult:
        self._workspace_parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        workspace = Path(
            tempfile.mkdtemp(
                prefix="publication-",
                dir=self._workspace_parent,
            )
        )

        try:
            self._clone(workspace)

            current_revision = self._git(
                workspace,
                "rev-parse",
                "HEAD",
            ).strip()

            if current_revision != change_set.base_revision:
                raise DisposableGitError(
                    "Disposable workspace HEAD does not match ChangeSet base_revision."
                )

            sink = GitRemoteChangeSink(
                workspace,
                remote_name=self._remote_name,
                base_branch=self._base_branch,
                author_name=self._author_name,
                author_email=self._author_email,
            )

            return sink._publish_sync(change_set)
        finally:
            shutil.rmtree(
                workspace,
                ignore_errors=True,
            )

    def _clone(
        self,
        workspace: Path,
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
                str(workspace),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise DisposableGitError(self._format_git_error(result))

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
            raise DisposableGitError(DisposableGitRemoteChangeSink._format_git_error(result))

        return result.stdout

    @staticmethod
    def _format_git_error(
        result: subprocess.CompletedProcess[str],
    ) -> str:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Git error"

        return f"Git command failed: {detail}"
