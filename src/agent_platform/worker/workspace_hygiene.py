from __future__ import annotations

import asyncio
import sys
from pathlib import Path


class WorkspaceHygieneError(RuntimeError):
    """Raised when deterministic Worker workspace hygiene cannot complete."""


async def apply_workspace_hygiene(
    workspace: Path,
) -> tuple[str, ...]:
    """Auto-fix and format only Python files changed by the Worker."""

    resolved = workspace.resolve(strict=True)

    if not resolved.is_dir():
        raise WorkspaceHygieneError("Worker workspace must be a directory.")

    paths = await _changed_python_paths(resolved)

    if not paths:
        return ()

    await _run(
        workspace=resolved,
        stage="ruff_check_fix",
        command=(
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--fix",
            "--exit-zero",
            "--",
            *paths,
        ),
    )

    await _run(
        workspace=resolved,
        stage="ruff_format",
        command=(
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--",
            *paths,
        ),
    )

    return paths


async def _changed_python_paths(
    workspace: Path,
) -> tuple[str, ...]:
    tracked = await _git_paths(
        workspace,
        (
            "diff",
            "--name-only",
            "-z",
            "--diff-filter=ACMRTUXB",
            "HEAD",
            "--",
            "*.py",
            "*.pyi",
        ),
    )

    untracked = await _git_paths(
        workspace,
        (
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            "*.py",
            "*.pyi",
        ),
    )

    return tuple(sorted(set((*tracked, *untracked))))


async def _git_paths(
    workspace: Path,
    args: tuple[str, ...],
) -> tuple[str, ...]:
    process = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=workspace,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, _ = await process.communicate()

    if process.returncode != 0:
        raise WorkspaceHygieneError("Unable to inspect Worker workspace changes.")

    return tuple(path.decode("utf-8") for path in stdout.split(b"\0") if path)


async def _run(
    *,
    workspace: Path,
    stage: str,
    command: tuple[str, ...],
) -> None:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=workspace,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    await process.communicate()

    if process.returncode != 0:
        raise WorkspaceHygieneError(f"Worker workspace hygiene failed at {stage}.")
