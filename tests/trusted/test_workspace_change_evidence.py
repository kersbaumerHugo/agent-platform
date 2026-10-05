from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from agent_platform.trust.workspace_change_evidence import (
    TrustedWorkspaceChangeCollector,
)


def git(
    repo: Path,
    *args: str,
) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    return result.stdout.strip()


def repository(
    tmp_path: Path,
) -> tuple[Path, str]:
    repo = tmp_path / "trusted"
    repo.mkdir()

    git(repo, "init")

    (repo / ".gitignore").write_text(
        ".pytest_cache/\n",
        encoding="utf-8",
    )
    (repo / "tracked.txt").write_text(
        "baseline\n",
        encoding="utf-8",
    )

    git(repo, "add", ".")
    git(repo, "commit", "-m", "baseline")

    revision = git(
        repo,
        "rev-parse",
        "HEAD",
    )

    return repo, revision


def candidate_from(
    trusted: Path,
    tmp_path: Path,
) -> Path:
    candidate = tmp_path / "candidate"

    subprocess.run(
        [
            "git",
            "clone",
            "--local",
            "--no-hardlinks",
            str(trusted),
            str(candidate),
        ],
        check=True,
        capture_output=True,
    )

    return candidate


def test_clean_workspace_has_no_change_evidence(
    tmp_path: Path,
) -> None:
    trusted, revision = repository(tmp_path)
    candidate = candidate_from(
        trusted,
        tmp_path,
    )

    collector = TrustedWorkspaceChangeCollector(
        trusted_repo_root=trusted,
    )

    evidence = collector.collect(
        workspace=candidate,
        base_revision=revision,
    )

    assert evidence.base_revision == revision
    assert evidence.changed_paths == ()


def test_tracked_modification_is_collected(
    tmp_path: Path,
) -> None:
    trusted, revision = repository(tmp_path)
    candidate = candidate_from(
        trusted,
        tmp_path,
    )

    (candidate / "tracked.txt").write_text(
        "changed\n",
        encoding="utf-8",
    )

    evidence = TrustedWorkspaceChangeCollector(
        trusted_repo_root=trusted,
    ).collect(
        workspace=candidate,
        base_revision=revision,
    )

    assert evidence.changed_paths == ("tracked.txt",)


def test_untracked_file_is_collected(
    tmp_path: Path,
) -> None:
    trusted, revision = repository(tmp_path)
    candidate = candidate_from(
        trusted,
        tmp_path,
    )

    (candidate / "new.txt").write_text(
        "new\n",
        encoding="utf-8",
    )

    evidence = TrustedWorkspaceChangeCollector(
        trusted_repo_root=trusted,
    ).collect(
        workspace=candidate,
        base_revision=revision,
    )

    assert evidence.changed_paths == ("new.txt",)


def test_deleted_file_is_collected(
    tmp_path: Path,
) -> None:
    trusted, revision = repository(tmp_path)
    candidate = candidate_from(
        trusted,
        tmp_path,
    )

    (candidate / "tracked.txt").unlink()

    evidence = TrustedWorkspaceChangeCollector(
        trusted_repo_root=trusted,
    ).collect(
        workspace=candidate,
        base_revision=revision,
    )

    assert evidence.changed_paths == ("tracked.txt",)


def test_ignored_runtime_artifact_does_not_count(
    tmp_path: Path,
) -> None:
    trusted, revision = repository(tmp_path)
    candidate = candidate_from(
        trusted,
        tmp_path,
    )

    cache = candidate / ".pytest_cache"
    cache.mkdir()
    (cache / "state").write_text(
        "runtime artifact",
        encoding="utf-8",
    )

    evidence = TrustedWorkspaceChangeCollector(
        trusted_repo_root=trusted,
    ).collect(
        workspace=candidate,
        base_revision=revision,
    )

    assert evidence.changed_paths == ()


def test_candidate_git_metadata_cannot_hide_change(
    tmp_path: Path,
) -> None:
    trusted, revision = repository(tmp_path)
    candidate = candidate_from(
        trusted,
        tmp_path,
    )

    (candidate / "tracked.txt").write_text(
        "candidate change\n",
        encoding="utf-8",
    )

    git(candidate, "add", "tracked.txt")
    git(
        candidate,
        "commit",
        "-m",
        "candidate tries to hide change",
    )

    evidence = TrustedWorkspaceChangeCollector(
        trusted_repo_root=trusted,
    ).collect(
        workspace=candidate,
        base_revision=revision,
    )

    assert evidence.changed_paths == ("tracked.txt",)


def test_candidate_index_cannot_hide_change(
    tmp_path: Path,
) -> None:
    trusted, revision = repository(tmp_path)
    candidate = candidate_from(
        trusted,
        tmp_path,
    )

    (candidate / "tracked.txt").write_text(
        "staged change\n",
        encoding="utf-8",
    )

    git(candidate, "add", "tracked.txt")

    evidence = TrustedWorkspaceChangeCollector(
        trusted_repo_root=trusted,
    ).collect(
        workspace=candidate,
        base_revision=revision,
    )

    assert evidence.changed_paths == ("tracked.txt",)


def test_candidate_git_directory_is_not_required(
    tmp_path: Path,
) -> None:
    trusted, revision = repository(tmp_path)
    candidate = candidate_from(
        trusted,
        tmp_path,
    )

    shutil.rmtree(candidate / ".git")

    (candidate / "tracked.txt").write_text(
        "changed without candidate git\n",
        encoding="utf-8",
    )

    evidence = TrustedWorkspaceChangeCollector(
        trusted_repo_root=trusted,
    ).collect(
        workspace=candidate,
        base_revision=revision,
    )

    assert evidence.changed_paths == ("tracked.txt",)


def test_candidate_gitignore_cannot_hide_untracked_change(tmp_path) -> None:
    import subprocess

    from agent_platform.trust.workspace_change_evidence import (
        TrustedWorkspaceChangeCollector,
    )

    trusted_repo = tmp_path / "trusted"
    trusted_repo.mkdir()

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=trusted_repo,
            check=True,
            capture_output=True,
            text=True,
        )

    git("init")
    git("config", "user.email", "tests@example.invalid")
    git("config", "user.name", "Agent Platform Tests")

    (trusted_repo / ".gitignore").write_text(
        "baseline.tmp\n",
        encoding="utf-8",
    )
    (trusted_repo / "tracked.txt").write_text(
        "trusted\n",
        encoding="utf-8",
    )

    git("add", ".")
    git("commit", "-m", "trusted base")

    base_revision = git("rev-parse", "HEAD").stdout.strip()

    workspace = tmp_path / "candidate"
    workspace.mkdir()

    (workspace / ".gitignore").write_text(
        "baseline.tmp\n",
        encoding="utf-8",
    )
    (workspace / "tracked.txt").write_text(
        "trusted\n",
        encoding="utf-8",
    )

    # The candidate attempts to hide a newly created file.
    (workspace / ".gitignore").write_text(
        "baseline.tmp\nhidden.txt\n",
        encoding="utf-8",
    )
    (workspace / "hidden.txt").write_text(
        "candidate-controlled payload\n",
        encoding="utf-8",
    )

    collector = TrustedWorkspaceChangeCollector(
        trusted_repo_root=trusted_repo,
    )

    evidence = collector.collect(
        workspace=workspace,
        base_revision=base_revision,
    )

    assert evidence.changed_paths == (
        ".gitignore",
        "hidden.txt",
    )
