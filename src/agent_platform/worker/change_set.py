from __future__ import annotations

import subprocess
from pathlib import Path

from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
)


class ChangeSetBuildError(RuntimeError):
    pass


class ChangeSetBuilder:
    """Build a ChangeSet from an untrusted Git working tree."""

    def __init__(
        self,
        repo_root: Path,
    ) -> None:
        self._repo_root = repo_root.resolve()
        self._verify_repo_root()

    def build(
        self,
        *,
        branch_name: str,
        commit_message: str,
    ) -> ChangeSet:
        base_revision = self._git(
            "rev-parse",
            "HEAD",
        ).strip()

        changes = self._collect_changes()

        if not changes:
            raise ChangeSetBuildError("Workspace contains no changes.")

        return ChangeSet(
            base_revision=base_revision,
            branch_name=branch_name,
            commit_message=commit_message,
            changes=tuple(
                sorted(
                    changes,
                    key=lambda change: change.path,
                )
            ),
        )

    def _collect_changes(
        self,
    ) -> list[FileChange]:
        changes: dict[str, FileChange] = {}

        tracked = self._git_bytes(
            "diff",
            "--name-status",
            "--no-renames",
            "-z",
            "HEAD",
            "--",
        )

        parts = tracked.split(b"\0")

        if parts and parts[-1] == b"":
            parts.pop()

        if len(parts) % 2 != 0:
            raise ChangeSetBuildError("Unexpected Git diff output.")

        for index in range(0, len(parts), 2):
            status = parts[index].decode(
                "ascii",
                errors="strict",
            )
            path = parts[index + 1].decode(
                "utf-8",
                errors="strict",
            )

            if status in {"A", "M"}:
                changes[path] = self._upsert(path)
            elif status == "D":
                changes[path] = FileChange(
                    path=path,
                    operation=FileChangeOperation.DELETE,
                )
            else:
                raise ChangeSetBuildError(f"Unsupported Git change status: {status}")

        untracked = self._git_bytes(
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        )

        for raw_path in untracked.split(b"\0"):
            if not raw_path:
                continue

            path = raw_path.decode(
                "utf-8",
                errors="strict",
            )

            changes[path] = self._upsert(path)

        return list(changes.values())

    def _upsert(
        self,
        path: str,
    ) -> FileChange:
        target = (self._repo_root / path).resolve()

        try:
            target.relative_to(self._repo_root)
        except ValueError as exc:
            raise ChangeSetBuildError(f"Path escapes workspace: {path}") from exc

        if target.is_symlink():
            raise ChangeSetBuildError(f"Symlinks are not supported: {path}")

        if not target.is_file():
            raise ChangeSetBuildError(f"Changed path is not a regular file: {path}")

        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ChangeSetBuildError(f"Changed file is not UTF-8 text: {path}") from exc

        return FileChange(
            path=path,
            operation=FileChangeOperation.UPSERT,
            content=content,
        )

    def _verify_repo_root(self) -> None:
        result = self._run_git(
            "rev-parse",
            "--show-toplevel",
        )

        if result.returncode != 0:
            raise ChangeSetBuildError("Workspace is not a Git repository.")

        actual = Path(result.stdout.strip()).resolve()

        if actual != self._repo_root:
            raise ChangeSetBuildError("Configured workspace must be the Git repository root.")

    def _git(
        self,
        *args: str,
    ) -> str:
        result = self._run_git(*args)

        if result.returncode != 0:
            raise ChangeSetBuildError(self._format_git_error(result))

        return result.stdout

    def _git_bytes(
        self,
        *args: str,
    ) -> bytes:
        result = subprocess.run(
            ["git", *args],
            cwd=self._repo_root,
            check=False,
            capture_output=True,
        )

        if result.returncode != 0:
            detail = (
                result.stderr.decode(
                    "utf-8",
                    errors="replace",
                ).strip()
                or result.stdout.decode(
                    "utf-8",
                    errors="replace",
                ).strip()
                or "unknown Git error"
            )

            raise ChangeSetBuildError(f"Git command failed: {detail}")

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
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Git error"

        return f"Git command failed: {detail}"
