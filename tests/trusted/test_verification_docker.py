from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agent_platform.trust.verification import (
    MAX_VERIFICATION_SUMMARY_CHARS,
)
from agent_platform.trust.verification_docker import (
    DockerCliVerificationLauncher,
    DockerVerificationConfig,
    DockerVerificationError,
    DockerVerificationProcessRunner,
)
from agent_platform.trust.verification_executor import (
    VerificationProcessOutcome,
    VerificationProcessResult,
)

PINNED_IMAGE = "sha256:" + ("a" * 64)


@dataclass
class RecordingLauncher:
    result: VerificationProcessResult = VerificationProcessResult(
        outcome=VerificationProcessOutcome.EXITED,
        exit_code=0,
    )
    commands: list[tuple[str, ...]] = field(default_factory=list)
    container_names: list[str] = field(default_factory=list)

    async def run(
        self,
        *,
        command: tuple[str, ...],
        container_name: str,
    ) -> VerificationProcessResult:
        self.commands.append(command)
        self.container_names.append(container_name)
        return self.result


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    return workspace


def _config(tmp_path: Path) -> DockerVerificationConfig:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    return DockerVerificationConfig(
        image=PINNED_IMAGE,
        runtime_root=runtime_root,
    )


@pytest.mark.asyncio
async def test_cli_launcher_captures_bounded_combined_failure_output() -> None:
    launcher = DockerCliVerificationLauncher(
        docker_binary="/usr/bin/docker",
        timeout_seconds=5.0,
        terminate_grace_seconds=1.0,
    )

    result = await launcher.run(
        command=(
            sys.executable,
            "-c",
            ("import sys;print('x' * 10000);print('stderr-marker', file=sys.stderr);sys.exit(1)"),
        ),
        container_name="not-used",
    )

    assert result.outcome is VerificationProcessOutcome.EXITED
    assert result.exit_code == 1
    assert len(result.output) <= MAX_VERIFICATION_SUMMARY_CHARS
    assert "stderr-marker" in result.output


def test_config_requires_pinned_image(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    with pytest.raises(ValueError, match="pinned"):
        DockerVerificationConfig(
            image="python:3.12",
            runtime_root=runtime_root,
        )


@pytest.mark.asyncio
async def test_runner_builds_hardened_docker_boundary(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    launcher = RecordingLauncher()
    runner = DockerVerificationProcessRunner(
        config=_config(tmp_path),
        launcher=launcher,
    )

    result = await runner.run(
        workspace=workspace,
        argv=("python", "-m", "pytest", "-q"),
    )

    assert result.exit_code == 0
    assert len(launcher.commands) == 1

    command = launcher.commands[0]
    joined = " ".join(command)

    assert command[:4] == (
        "/usr/bin/docker",
        "run",
        "--rm",
        "--pull",
    )
    assert "never" in command
    assert "--network none" in joined
    assert "--read-only" in command
    assert "--cap-drop ALL" in joined
    assert "--security-opt no-new-privileges" in joined
    assert "--pids-limit 128" in joined
    assert "--memory 1g" in joined
    assert "--cpus 2" in joined
    assert "--workdir /workspace" in joined
    assert f"type=bind,src={workspace},dst=/workspace" in command
    assert f"type=bind,src={workspace / '.git'},dst=/workspace/.git,readonly" in command
    assert "HOME=/tmp" in command
    assert "TMPDIR=/tmp" in command
    assert "PYTHONUTF8=1" in command
    assert "PYTHONPATH=/workspace/src" in command
    assert "PIP_NO_INDEX=1" in command
    assert "PIP_FIND_LINKS=/opt/wheelhouse" in command
    assert "/tmp:rw,exec,nosuid,nodev,size=256m" in command
    assert PINNED_IMAGE in command
    assert command[-4:] == (
        "python",
        "-m",
        "pytest",
        "-q",
    )

    assert "docker.sock" not in joined
    assert "trusted-change.sock" not in joined
    assert "GITHUB_TOKEN" not in joined
    assert "GH_TOKEN" not in joined
    assert "MODEL_GATEWAY_API_KEY" not in joined
    assert "--privileged" not in command


@pytest.mark.asyncio
async def test_runner_uses_workspace_owner_and_unique_container_name(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    launcher = RecordingLauncher()
    runner = DockerVerificationProcessRunner(
        config=_config(tmp_path),
        launcher=launcher,
    )

    await runner.run(
        workspace=workspace,
        argv=("git", "diff", "--check"),
    )
    await runner.run(
        workspace=workspace,
        argv=("git", "diff", "--check"),
    )

    first = launcher.commands[0]
    user_index = first.index("--user")
    stat = workspace.stat()

    assert first[user_index + 1] == f"{stat.st_uid}:{stat.st_gid}"
    assert len(set(launcher.container_names)) == 2
    assert all(name.startswith("agent-platform-verifier-") for name in launcher.container_names)


@pytest.mark.asyncio
async def test_runner_rejects_workspace_without_git_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runner = DockerVerificationProcessRunner(
        config=_config(tmp_path),
        launcher=RecordingLauncher(),
    )

    with pytest.raises(
        DockerVerificationError,
        match=r"\.git",
    ):
        await runner.run(
            workspace=workspace,
            argv=("git", "diff", "--check"),
        )


@pytest.mark.asyncio
async def test_runner_rejects_symlinked_git_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    actual_git = tmp_path / "actual-git"
    actual_git.mkdir()
    (workspace / ".git").symlink_to(
        actual_git,
        target_is_directory=True,
    )
    runner = DockerVerificationProcessRunner(
        config=_config(tmp_path),
        launcher=RecordingLauncher(),
    )

    with pytest.raises(
        DockerVerificationError,
        match=r"\.git",
    ):
        await runner.run(
            workspace=workspace,
            argv=("git", "diff", "--check"),
        )
