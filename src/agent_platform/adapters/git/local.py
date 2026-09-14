from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
    PublicationResult,
)


class LocalGitError(RuntimeError):
    pass


class LocalGitChangeSink:
    """Publish an accepted ChangeSet into a disposable local Git workspace."""

    def __init__(
        self,
        repo_root: Path,
        *,
        author_name: str = "Agent Platform",
        author_email: str = "agent-platform@localhost",
    ) -> None:
        self._repo_root = repo_root.resolve()
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
        self._verify_repository()
        self._verify_clean_workspace()
        self._verify_base_revision(change_set.base_revision)
        self._verify_branch_name(change_set.branch_name)

        self._git(
            "switch",
            "-c",
            change_set.branch_name,
        )

        for change in change_set.changes:
            self._apply_change(change)

        self._git("add", "-A", "--", ".")

        diff_result = self._run_git(
            "diff",
            "--cached",
            "--quiet",
        )

        if diff_result.returncode == 0:
            raise LocalGitError("ChangeSet produced no Git changes.")

        if diff_result.returncode != 1:
            raise LocalGitError(self._format_git_error(diff_result))

        self._git(
            "-c",
            f"user.name={self._author_name}",
            "-c",
            f"user.email={self._author_email}",
            "commit",
            "-m",
            change_set.commit_message,
        )

        commit_sha = self._git(
            "rev-parse",
            "HEAD",
        ).strip()

        return PublicationResult(reference=f"git:{commit_sha}")

    def _verify_repository(self) -> None:
        top_level = Path(
            self._git(
                "rev-parse",
                "--show-toplevel",
            ).strip()
        ).resolve()

        if top_level != self._repo_root:
            raise LocalGitError("Configured repository root does not match Git root.")

    def _verify_clean_workspace(self) -> None:
        status = self._git(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )

        if status.strip():
            raise LocalGitError("Git workspace must be clean before publication.")

    def _verify_base_revision(
        self,
        expected_revision: str,
    ) -> None:
        current_revision = self._git(
            "rev-parse",
            "HEAD",
        ).strip()

        if current_revision != expected_revision:
            raise LocalGitError("Workspace HEAD does not match ChangeSet base_revision.")

    def _verify_branch_name(
        self,
        branch_name: str,
    ) -> None:
        if branch_name.startswith("-"):
            raise LocalGitError("Invalid Git branch name.")

        result = self._run_git(
            "check-ref-format",
            "--branch",
            branch_name,
        )

        if result.returncode != 0:
            raise LocalGitError("Invalid Git branch name.")

    def _apply_change(
        self,
        change: FileChange,
    ) -> None:
        target = self._safe_target(change.path)

        if change.operation is FileChangeOperation.UPSERT:
            assert change.content is not None

            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            target.write_text(
                change.content,
                encoding="utf-8",
            )
            return

        if change.operation is FileChangeOperation.DELETE:
            if not target.exists():
                raise LocalGitError(f"Cannot delete missing file: {change.path}")

            if not target.is_file():
                raise LocalGitError(f"Delete target is not a file: {change.path}")

            target.unlink()
            return

        raise LocalGitError(f"Unsupported file operation: {change.operation}")

    def _safe_target(
        self,
        relative_path: str,
    ) -> Path:
        target = (self._repo_root / relative_path).resolve(strict=False)

        try:
            target.relative_to(self._repo_root)
        except ValueError as exc:
            raise LocalGitError("Change path escapes repository root.") from exc

        return target

    def _git(
        self,
        *args: str,
    ) -> str:
        result = self._run_git(*args)

        if result.returncode != 0:
            raise LocalGitError(self._format_git_error(result))

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
