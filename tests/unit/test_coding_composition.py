from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_platform.adapters.capabilities.coding import (
    SupervisedCodingCapability,
)
from agent_platform.api.coding_composition import (
    build_supervised_coding_capability,
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


def _trusted_repo(
    tmp_path: Path,
) -> Path:
    repo = tmp_path / "trusted"
    repo.mkdir()

    _git(repo, "init", "-b", "main")

    (repo / "README.md").write_text(
        "# coding composition test\n",
        encoding="utf-8",
    )

    _git(repo, "add", "README.md")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "baseline",
    )

    return repo


def _env(
    tmp_path: Path,
) -> dict[str, str]:
    repo = _trusted_repo(tmp_path)

    worker_root = tmp_path / "worker"
    worker_root.mkdir()

    verifier_runtime = tmp_path / "verifier-runtime"
    verifier_runtime.mkdir()

    return {
        "AGENT_PLATFORM_CODING_REPOSITORY_URL": str(repo),
        "AGENT_PLATFORM_CODING_TRUSTED_REPOSITORY_PATH": (str(repo)),
        "AGENT_PLATFORM_CODING_WORKSPACE_PARENT": (str(worker_root)),
        "AGENT_PLATFORM_CODING_SANDBOX_SOCKET": str(tmp_path / "sandbox.sock"),
        "AGENT_PLATFORM_CODING_VERIFICATION_WORKSPACE_PARENT": str(tmp_path / "verification"),
        "AGENT_PLATFORM_CODING_VERIFIER_RUNTIME_ROOT": str(verifier_runtime),
        "AGENT_PLATFORM_CODING_VERIFIER_IMAGE": ("sha256:" + "a" * 64),
        "AGENT_PLATFORM_CODING_PUBLISHER_SOCKET": str(tmp_path / "publisher.sock"),
        "AGENT_PLATFORM_CODING_BASE_BRANCH": "main",
    }


def test_builds_supervised_coding_capability(
    tmp_path: Path,
) -> None:
    capability = build_supervised_coding_capability(_env(tmp_path))

    assert isinstance(
        capability,
        SupervisedCodingCapability,
    )
    assert capability.definition.name == "coding.execute"


def test_missing_configuration_fails_closed(
    tmp_path: Path,
) -> None:
    env = _env(tmp_path)
    del env["AGENT_PLATFORM_CODING_REPOSITORY_URL"]

    with pytest.raises(
        ValueError,
        match="AGENT_PLATFORM_CODING_REPOSITORY_URL",
    ):
        build_supervised_coding_capability(env)
