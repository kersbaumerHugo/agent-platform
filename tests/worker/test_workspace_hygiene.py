from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_platform.worker.workspace_hygiene import (
    apply_workspace_hygiene,
)


def _git(
    repo: Path,
    *args: str,
) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    _git(repo, "init", "-b", "main")

    tracked = repo / "tracked.py"
    tracked.write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    _git(repo, "add", "tracked.py")
    _git(
        repo,
        "-c",
        "user.name=Worker Hygiene Test",
        "-c",
        "user.email=worker-hygiene@example.invalid",
        "commit",
        "-m",
        "baseline",
    )

    return repo


@pytest.mark.asyncio
async def test_hygiene_fixes_changed_and_untracked_python_files(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)

    (repo / "tracked.py").write_text(
        "import os\n\nVALUE=2\n",
        encoding="utf-8",
    )
    (repo / "new_file.py").write_text(
        "import sys\n\nOTHER=3\n",
        encoding="utf-8",
    )

    paths = await apply_workspace_hygiene(repo)

    assert paths == (
        "new_file.py",
        "tracked.py",
    )
    assert (repo / "tracked.py").read_text(
        encoding="utf-8",
    ) == "VALUE = 2\n"
    assert (repo / "new_file.py").read_text(
        encoding="utf-8",
    ) == "OTHER = 3\n"


@pytest.mark.asyncio
async def test_hygiene_does_nothing_without_python_changes(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)

    assert await apply_workspace_hygiene(repo) == ()


@pytest.mark.asyncio
async def test_hygiene_includes_staged_python_changes(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)

    (repo / "tracked.py").write_text(
        "import os\n\nVALUE=4\n",
        encoding="utf-8",
    )

    _git(repo, "add", "tracked.py")

    paths = await apply_workspace_hygiene(repo)

    assert paths == ("tracked.py",)
    assert (repo / "tracked.py").read_text(
        encoding="utf-8",
    ) == "VALUE = 4\n"
