from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from agent_platform.trust.change_set_identity import (
    ChangeSetIdentity,
    identify_change_set,
)
from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
)


class ChangeSetMaterializationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MaterializedChangeSet:
    workspace: Path
    identity: ChangeSetIdentity
    base_revision: str


class DisposableChangeSetMaterializer:
    """Materialize one exact ChangeSet from a trusted local Git baseline."""

    def __init__(
        self,
        *,
        trusted_repo_root: Path,
        workspace_parent: Path,
        git_binary: str = "git",
    ) -> None:
        if trusted_repo_root.is_symlink():
            raise ValueError("trusted_repo_root must not be a symlink.")

        if workspace_parent.is_symlink():
            raise ValueError("workspace_parent must not be a symlink.")

        if not git_binary.strip() or "\x00" in git_binary:
            raise ValueError("git_binary must not be empty.")

        try:
            trusted_root = trusted_repo_root.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError("trusted_repo_root must exist.") from exc

        if not trusted_root.is_dir():
            raise ValueError("trusted_repo_root must be a directory.")

        workspace_parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        resolved_parent = workspace_parent.resolve(strict=True)

        if not resolved_parent.is_dir():
            raise ValueError("workspace_parent must be a directory.")

        self._trusted_repo_root = trusted_root
        self._workspace_parent = resolved_parent
        self._git_binary = git_binary

        self._verify_trusted_repository()

    @contextmanager
    def materialize(
        self,
        change_set: ChangeSet,
    ) -> Iterator[MaterializedChangeSet]:
        self._verify_trusted_base(change_set.base_revision)

        identity = identify_change_set(change_set)
        workspace = Path(
            tempfile.mkdtemp(
                prefix=f"verification-{identity.sha256[:12]}-",
                dir=self._workspace_parent,
            )
        )

        try:
            self._clone_without_shared_objects(workspace)
            self._git(
                workspace,
                "remote",
                "remove",
                "origin",
            )
            self._git(
                workspace,
                "checkout",
                "--detach",
                change_set.base_revision,
            )

            actual_base = self._git(
                workspace,
                "rev-parse",
                "HEAD",
            ).strip()

            if actual_base != change_set.base_revision:
                raise ChangeSetMaterializationError(
                    "Materialized workspace HEAD does not match ChangeSet base_revision."
                )

            for change in change_set.changes:
                self._apply_change(
                    workspace,
                    change,
                )

            materialized = MaterializedChangeSet(
                workspace=workspace,
                identity=identity,
                base_revision=actual_base,
            )
            self.assert_exact(
                materialized=materialized,
                change_set=change_set,
            )

            yield materialized
        finally:
            shutil.rmtree(
                workspace,
                ignore_errors=True,
            )

    def assert_exact(
        self,
        *,
        materialized: MaterializedChangeSet,
        change_set: ChangeSet,
    ) -> None:
        """Fail closed if the verification workspace drifted from the exact ChangeSet."""

        expected_identity = identify_change_set(change_set)

        if materialized.identity != expected_identity:
            raise ChangeSetMaterializationError(
                "Materialized ChangeSet identity does not match requested ChangeSet."
            )

        actual_base = self._git(
            materialized.workspace,
            "rev-parse",
            "HEAD",
        ).strip()

        if actual_base != change_set.base_revision or actual_base != materialized.base_revision:
            raise ChangeSetMaterializationError(
                "Materialized workspace HEAD changed after verification."
            )

        self._verify_exact_materialization(
            workspace=materialized.workspace,
            change_set=change_set,
            expected_identity=expected_identity,
        )

    def _verify_trusted_repository(self) -> None:
        top_level = Path(
            self._git(
                self._trusted_repo_root,
                "rev-parse",
                "--show-toplevel",
            ).strip()
        ).resolve()

        if top_level != self._trusted_repo_root:
            raise ValueError("trusted_repo_root must be the Git repository root.")

    def _verify_trusted_base(
        self,
        expected_revision: str,
    ) -> None:
        actual_revision = self._git(
            self._trusted_repo_root,
            "rev-parse",
            "HEAD",
        ).strip()

        if actual_revision != expected_revision:
            raise ChangeSetMaterializationError(
                "ChangeSet base_revision does not match the trusted repository HEAD."
            )

    def _clone_without_shared_objects(
        self,
        workspace: Path,
    ) -> None:
        self._run_checked(
            cwd=self._workspace_parent,
            argv=(
                self._git_binary,
                "-c",
                "core.hooksPath=/dev/null",
                "clone",
                "--local",
                "--no-hardlinks",
                "--no-checkout",
                "--no-tags",
                str(self._trusted_repo_root),
                str(workspace),
            ),
        )

    def _apply_change(
        self,
        workspace: Path,
        change: FileChange,
    ) -> None:
        target = self._safe_target(
            workspace,
            change.path,
        )

        if change.operation is FileChangeOperation.UPSERT:
            assert change.content is not None

            if target.exists() and target.is_symlink():
                raise ChangeSetMaterializationError(f"UPSERT target is a symlink: {change.path}")

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
                raise ChangeSetMaterializationError(f"Cannot delete missing file: {change.path}")

            if target.is_symlink() or not target.is_file():
                raise ChangeSetMaterializationError(
                    f"Delete target is not a regular file: {change.path}"
                )

            target.unlink()
            return

        raise ChangeSetMaterializationError(f"Unsupported file operation: {change.operation}")

    def _verify_exact_materialization(
        self,
        *,
        workspace: Path,
        change_set: ChangeSet,
        expected_identity: ChangeSetIdentity,
    ) -> None:
        actual_paths = self._changed_paths(workspace)
        expected_paths = {change.path for change in change_set.changes}

        if actual_paths != expected_paths:
            raise ChangeSetMaterializationError(
                "Materialized Git changes do not match ChangeSet paths."
            )

        reconstructed: list[FileChange] = []

        for path in sorted(actual_paths):
            target = self._safe_target(
                workspace,
                path,
            )

            if target.exists():
                if target.is_symlink() or not target.is_file():
                    raise ChangeSetMaterializationError(
                        f"Materialized target is not a regular file: {path}"
                    )

                try:
                    content = target.read_text(encoding="utf-8")
                except UnicodeDecodeError as exc:
                    raise ChangeSetMaterializationError(
                        f"Materialized file is not UTF-8 text: {path}"
                    ) from exc

                reconstructed.append(
                    FileChange(
                        path=path,
                        operation=FileChangeOperation.UPSERT,
                        content=content,
                    )
                )
            else:
                reconstructed.append(
                    FileChange(
                        path=path,
                        operation=FileChangeOperation.DELETE,
                    )
                )

        materialized_change_set = ChangeSet(
            base_revision=change_set.base_revision,
            branch_name=change_set.branch_name,
            commit_message=change_set.commit_message,
            changes=tuple(reconstructed),
        )

        if identify_change_set(materialized_change_set) != expected_identity:
            raise ChangeSetMaterializationError(
                "Materialized ChangeSet identity does not match requested ChangeSet."
            )

    def _changed_paths(
        self,
        workspace: Path,
    ) -> set[str]:
        tracked = self._git_bytes(
            workspace,
            "diff",
            "--name-only",
            "-z",
            "HEAD",
            "--",
        )
        untracked = self._git_bytes(
            workspace,
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        )

        paths: set[str] = set()

        for raw_path in tracked.split(b"\0") + untracked.split(b"\0"):
            if not raw_path:
                continue

            try:
                path = raw_path.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ChangeSetMaterializationError(
                    "Materialized Git path is not valid UTF-8."
                ) from exc

            self._validate_relative_path(path)
            paths.add(path)

        return paths

    def _safe_target(
        self,
        workspace: Path,
        relative_path: str,
    ) -> Path:
        pure_path = self._validate_relative_path(relative_path)

        current = workspace

        for part in pure_path.parts[:-1]:
            current = current / part

            if current.is_symlink():
                raise ChangeSetMaterializationError(
                    f"Change path traverses a symlink: {relative_path}"
                )

        target = workspace.joinpath(*pure_path.parts)

        try:
            resolved = target.resolve(strict=False)
            resolved.relative_to(workspace)
        except ValueError as exc:
            raise ChangeSetMaterializationError(
                f"Change path escapes workspace: {relative_path}"
            ) from exc

        return target

    @staticmethod
    def _validate_relative_path(
        relative_path: str,
    ) -> PurePosixPath:
        if not relative_path or "\x00" in relative_path:
            raise ChangeSetMaterializationError("Change path is invalid.")

        path = PurePosixPath(relative_path)

        if path.is_absolute():
            raise ChangeSetMaterializationError("Change path must be relative.")

        if not path.parts or any(part in {".", ".."} for part in path.parts):
            raise ChangeSetMaterializationError("Change path is not canonical.")

        if path.as_posix() != relative_path:
            raise ChangeSetMaterializationError("Change path is not canonical.")

        if path.parts[0] == ".git":
            raise ChangeSetMaterializationError("ChangeSet must not modify Git metadata.")

        return path

    def _git(
        self,
        repo: Path,
        *args: str,
    ) -> str:
        result = self._run_checked(
            cwd=repo,
            argv=(
                self._git_binary,
                "-c",
                "core.hooksPath=/dev/null",
                *args,
            ),
        )

        return result.stdout

    def _git_bytes(
        self,
        repo: Path,
        *args: str,
    ) -> bytes:
        result = subprocess.run(
            [
                self._git_binary,
                "-c",
                "core.hooksPath=/dev/null",
                *args,
            ],
            cwd=repo,
            check=False,
            capture_output=True,
            env=self._git_environment(),
        )

        if result.returncode != 0:
            raise ChangeSetMaterializationError("Git command failed.")

        return result.stdout

    def _run_checked(
        self,
        *,
        cwd: Path,
        argv: tuple[str, ...],
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            list(argv),
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            env=self._git_environment(),
        )

        if result.returncode != 0:
            raise ChangeSetMaterializationError("Git command failed.")

        return result

    @staticmethod
    def _git_environment() -> dict[str, str]:
        path = os.environ.get("PATH", "")

        if not path:
            raise RuntimeError("PATH is required for Git materialization.")

        return {
            "PATH": path,
            "HOME": "/nonexistent",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C.UTF-8",
        }
