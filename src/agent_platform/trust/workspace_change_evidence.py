from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_SHA1_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class WorkspaceChangeEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkspaceChangeEvidence:
    base_revision: str
    changed_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _SHA1_PATTERN.fullmatch(self.base_revision):
            raise ValueError("base_revision must be a full lowercase Git SHA-1.")

        if self.changed_paths != tuple(sorted(set(self.changed_paths))):
            raise ValueError("changed_paths must be unique and sorted.")


class TrustedWorkspaceChangeCollector:
    """Collect candidate changes against a trusted Git base.

    Candidate Git metadata is never consulted. The collector uses
    the trusted repository object database and a fresh temporary
    index populated directly from the expected base revision.
    """

    def __init__(
        self,
        *,
        trusted_repo_root: Path,
        git_binary: str = "git",
    ) -> None:
        if trusted_repo_root.is_symlink():
            raise ValueError("trusted_repo_root must not be a symlink.")

        if not git_binary.strip() or "\x00" in git_binary:
            raise ValueError("git_binary must not be empty.")

        try:
            root = trusted_repo_root.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError("trusted_repo_root must exist.") from exc

        if not root.is_dir():
            raise ValueError("trusted_repo_root must be a directory.")

        self._trusted_repo_root = root
        self._git_binary = git_binary

        top_level = Path(
            self._trusted_git(
                "rev-parse",
                "--show-toplevel",
            ).strip()
        ).resolve()

        if top_level != root:
            raise ValueError("trusted_repo_root must be the Git repository root.")

        git_dir_raw = self._trusted_git(
            "rev-parse",
            "--absolute-git-dir",
        ).strip()

        self._git_dir = Path(git_dir_raw).resolve(strict=True)

        if not self._git_dir.is_dir():
            raise ValueError("Trusted Git directory must be a directory.")

    def collect(
        self,
        *,
        workspace: Path,
        base_revision: str,
    ) -> WorkspaceChangeEvidence:
        self._validate_base_revision(base_revision)

        resolved_workspace = self._resolve_workspace(workspace)

        actual_revision = self._trusted_git(
            "rev-parse",
            f"{base_revision}^{{commit}}",
        ).strip()

        if actual_revision != base_revision:
            raise WorkspaceChangeEvidenceError("base_revision is not the exact trusted commit.")

        with tempfile.TemporaryDirectory(prefix="goal-acceptance-index-") as temporary:
            index_path = Path(temporary) / "index"

            environment = self._candidate_environment(
                workspace=resolved_workspace,
                index_path=index_path,
            )

            self._run_checked(
                cwd=self._trusted_repo_root,
                argv=(
                    self._git_binary,
                    "-c",
                    "core.hooksPath=/dev/null",
                    "read-tree",
                    base_revision,
                ),
                env=environment,
            )

            self._refresh_index(
                workspace=resolved_workspace,
                environment=environment,
            )

            tracked = self._run_bytes(
                cwd=resolved_workspace,
                argv=(
                    self._git_binary,
                    "-c",
                    "core.hooksPath=/dev/null",
                    "diff-files",
                    "--name-only",
                    "-z",
                    "--",
                ),
                env=environment,
            )

            # Collect every untracked path first. Candidate-controlled
            # ignore rules must not participate in trusted evidence.
            untracked = self._run_bytes(
                cwd=resolved_workspace,
                argv=(
                    self._git_binary,
                    "-c",
                    "core.hooksPath=/dev/null",
                    "ls-files",
                    "--others",
                    "-z",
                    "--",
                ),
                env=environment,
            )

            # Runtime artifacts may still be ignored, but only according
            # to .gitignore files committed in the trusted base revision.
            untracked = self._filter_with_trusted_ignore_rules(
                raw_paths=untracked,
                base_revision=base_revision,
                temporary_root=Path(temporary),
            )

        paths: set[str] = set()

        for raw_path in tracked.split(b"\0") + untracked.split(b"\0"):
            if not raw_path:
                continue

            try:
                path = raw_path.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise (
                    WorkspaceChangeEvidenceError("Candidate Git path is not valid UTF-8.")
                ) from exc

            self._validate_relative_path(path)
            paths.add(path)

        return WorkspaceChangeEvidence(
            base_revision=base_revision,
            changed_paths=tuple(sorted(paths)),
        )

    def _trusted_git(
        self,
        *args: str,
    ) -> str:
        result = self._run_checked(
            cwd=self._trusted_repo_root,
            argv=(
                self._git_binary,
                "-c",
                "core.hooksPath=/dev/null",
                *args,
            ),
            env=self._base_environment(),
        )

        return result.stdout

    @staticmethod
    def _resolve_workspace(
        workspace: Path,
    ) -> Path:
        if workspace.is_symlink():
            raise ValueError("Candidate workspace must not be a symlink.")

        try:
            resolved = workspace.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError("Candidate workspace must exist.") from exc

        if not resolved.is_dir():
            raise ValueError("Candidate workspace must be a directory.")

        return resolved

    @staticmethod
    def _validate_base_revision(
        revision: str,
    ) -> None:
        if not _SHA1_PATTERN.fullmatch(revision):
            raise ValueError("base_revision must be a full lowercase Git SHA-1.")

    @staticmethod
    def _validate_relative_path(
        raw: str,
    ) -> None:
        if not raw or "\x00" in raw:
            raise WorkspaceChangeEvidenceError("Candidate change path is invalid.")

        path = PurePosixPath(raw)

        if path.is_absolute():
            raise WorkspaceChangeEvidenceError("Candidate change path must be relative.")

        if (
            not path.parts
            or any(part in {".", ".."} for part in path.parts)
            or path.as_posix() != raw
        ):
            raise WorkspaceChangeEvidenceError("Candidate change path is not canonical.")

        if path.parts[0] == ".git":
            raise WorkspaceChangeEvidenceError(
                "Candidate change evidence must not include Git metadata."
            )

    def _refresh_index(
        self,
        *,
        workspace: Path,
        environment: dict[str, str],
    ) -> None:
        result = subprocess.run(
            [
                self._git_binary,
                "-c",
                "core.hooksPath=/dev/null",
                "update-index",
                "--refresh",
            ],
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        # `git update-index --refresh` returns 1 when tracked files
        # legitimately differ from the temporary index.
        if result.returncode not in {0, 1}:
            raise WorkspaceChangeEvidenceError("Trusted Git index refresh failed.")

    def _filter_with_trusted_ignore_rules(
        self,
        *,
        raw_paths: bytes,
        base_revision: str,
        temporary_root: Path,
    ) -> bytes:
        candidate_paths = tuple(raw_path for raw_path in raw_paths.split(b"\0") if raw_path)

        if not candidate_paths:
            return b""

        ignore_worktree = temporary_root / "trusted-ignore-worktree"
        ignore_worktree.mkdir()

        # Use an isolated temporary Git repository so ignore semantics
        # cannot inherit candidate metadata or trusted-repo-local
        # .git/info/exclude state.
        self._run_checked(
            cwd=ignore_worktree,
            argv=(
                self._git_binary,
                "init",
                "--quiet",
            ),
            env=self._base_environment(),
        )

        self._materialize_trusted_gitignores(
            base_revision=base_revision,
            destination=ignore_worktree,
        )

        payload = b"\0".join(candidate_paths) + b"\0"

        result = subprocess.run(
            [
                self._git_binary,
                "-c",
                "core.hooksPath=/dev/null",
                "check-ignore",
                "--no-index",
                "-z",
                "--stdin",
            ],
            cwd=ignore_worktree,
            check=False,
            capture_output=True,
            input=payload,
            env=self._base_environment(),
        )

        # check-ignore returns:
        #   0 -> at least one path matched an ignore rule
        #   1 -> no paths matched
        #  >1 -> operational failure
        if result.returncode not in {0, 1}:
            raise WorkspaceChangeEvidenceError("Trusted Git ignore evaluation failed.")

        ignored_paths = {raw_path for raw_path in result.stdout.split(b"\0") if raw_path}

        visible_paths = tuple(
            raw_path for raw_path in candidate_paths if raw_path not in ignored_paths
        )

        return b"".join(raw_path + b"\0" for raw_path in visible_paths)

    def _materialize_trusted_gitignores(
        self,
        *,
        base_revision: str,
        destination: Path,
    ) -> None:
        tree = self._run_bytes(
            cwd=self._trusted_repo_root,
            argv=(
                self._git_binary,
                "-c",
                "core.hooksPath=/dev/null",
                "ls-tree",
                "-r",
                "-z",
                base_revision,
            ),
            env=self._base_environment(),
        )

        for entry in tree.split(b"\0"):
            if not entry:
                continue

            try:
                metadata, raw_path = entry.split(b"\t", 1)
                mode, object_type, object_id = metadata.split(b" ", 2)
            except ValueError as exc:
                raise WorkspaceChangeEvidenceError("Trusted Git tree entry is malformed.") from exc

            try:
                path = raw_path.decode("utf-8")
                object_name = object_id.decode("ascii")
            except UnicodeDecodeError as exc:
                raise WorkspaceChangeEvidenceError(
                    "Trusted Git tree metadata is not valid UTF-8/ASCII."
                ) from exc

            self._validate_relative_path(path)

            posix_path = PurePosixPath(path)

            if posix_path.name != ".gitignore":
                continue

            # Git does not follow symlinks when reading .gitignore files.
            if object_type != b"blob" or mode == b"120000":
                continue

            contents = self._run_bytes(
                cwd=self._trusted_repo_root,
                argv=(
                    self._git_binary,
                    "-c",
                    "core.hooksPath=/dev/null",
                    "cat-file",
                    "blob",
                    object_name,
                ),
                env=self._base_environment(),
            )

            target = destination.joinpath(*posix_path.parts)
            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            target.write_bytes(contents)

    def _candidate_environment(
        self,
        *,
        workspace: Path,
        index_path: Path,
    ) -> dict[str, str]:
        environment = self._base_environment()

        environment.update(
            {
                "GIT_DIR": str(self._git_dir),
                "GIT_WORK_TREE": str(workspace),
                "GIT_INDEX_FILE": str(index_path),
            }
        )

        return environment

    @staticmethod
    def _base_environment() -> dict[str, str]:
        path = os.environ.get("PATH", "")

        if not path:
            raise RuntimeError("PATH is required for trusted change collection.")

        return {
            "PATH": path,
            "HOME": "/nonexistent",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C.UTF-8",
        }

    @staticmethod
    def _run_checked(
        *,
        cwd: Path,
        argv: tuple[str, ...],
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            list(argv),
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        if result.returncode != 0:
            raise WorkspaceChangeEvidenceError("Trusted Git command failed.")

        return result

    @staticmethod
    def _run_bytes(
        *,
        cwd: Path,
        argv: tuple[str, ...],
        env: dict[str, str],
    ) -> bytes:
        result = subprocess.run(
            list(argv),
            cwd=cwd,
            check=False,
            capture_output=True,
            env=env,
        )

        if result.returncode != 0:
            raise WorkspaceChangeEvidenceError("Trusted Git command failed.")

        return result.stdout
