from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from agent_platform.adapters.git.local import LocalGitChangeSink
from agent_platform.trust.publisher import (
    ChangeSet,
    PublicationResult,
)


class GitRemoteError(RuntimeError):
    pass


class GitRemoteChangeSink:
    """Publish an accepted ChangeSet to a Git remote without force-updating refs."""

    def __init__(
        self,
        repo_root: Path,
        *,
        remote_name: str = "origin",
        author_name: str = "Agent Platform",
        author_email: str = "agent-platform@localhost",
    ) -> None:
        self._repo_root = repo_root.resolve()
        self._remote_name = remote_name
        self._local_sink = LocalGitChangeSink(
            repo_root,
            author_name=author_name,
            author_email=author_email,
        )

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
        self._verify_remote()
        self._verify_branch_name(change_set.branch_name)
        self._verify_remote_branch_absent(change_set.branch_name)

        local_result = asyncio.run(self._local_sink.publish(change_set))

        commit_sha = local_result.reference.removeprefix("git:")

        self._git(
            "push",
            "--porcelain",
            "--set-upstream",
            self._remote_name,
            f"HEAD:refs/heads/{change_set.branch_name}",
        )

        return PublicationResult(
            reference=(f"git-remote:{self._remote_name}/{change_set.branch_name}@{commit_sha}")
        )

    def _verify_remote(self) -> None:
        result = self._run_git(
            "remote",
            "get-url",
            self._remote_name,
        )

        if result.returncode != 0:
            raise GitRemoteError(f"Git remote is not configured: {self._remote_name}")

    def _verify_branch_name(
        self,
        branch_name: str,
    ) -> None:
        result = self._run_git(
            "check-ref-format",
            "--branch",
            branch_name,
        )

        if result.returncode != 0:
            raise GitRemoteError("Invalid Git branch name.")

    def _verify_remote_branch_absent(
        self,
        branch_name: str,
    ) -> None:
        result = self._run_git(
            "ls-remote",
            "--exit-code",
            "--heads",
            self._remote_name,
            f"refs/heads/{branch_name}",
        )

        if result.returncode == 0:
            raise GitRemoteError(f"Remote branch already exists: {branch_name}")

        if result.returncode != 2:
            raise GitRemoteError(self._format_git_error(result))

    def _git(
        self,
        *args: str,
    ) -> str:
        result = self._run_git(*args)

        if result.returncode != 0:
            raise GitRemoteError(self._format_git_error(result))

        return result.stdout

    def _run_git(
        self,
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self._repo_root,
            check=False,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def _format_git_error(
        result: subprocess.CompletedProcess[str],
    ) -> str:
        detail = result.stderr.strip() or result.stdout.strip()
        return f"Git command failed: {detail}"
