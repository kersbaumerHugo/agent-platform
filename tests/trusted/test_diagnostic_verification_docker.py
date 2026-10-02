from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agent_platform.trust.diagnostic_verification import (
    DiagnosticVerificationResult,
)
from agent_platform.trust.diagnostic_verification_docker import (
    DockerDiagnosticVerificationAuthority,
)
from agent_platform.trust.verification_docker import (
    DockerVerificationConfig,
)

PINNED_IMAGE = "sha256:" + ("a" * 64)


@dataclass
class RecordingLauncher:
    result: DiagnosticVerificationResult = DiagnosticVerificationResult(
        exit_code=0,
        output="682 passed",
    )
    commands: list[tuple[str, ...]] = field(default_factory=list)
    container_names: list[str] = field(default_factory=list)

    async def run(
        self,
        *,
        command: tuple[str, ...],
        container_name: str,
    ) -> DiagnosticVerificationResult:
        self.commands.append(command)
        self.container_names.append(container_name)
        return self.result


def _workspace(
    tmp_path: Path,
) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    return workspace


def _config(
    tmp_path: Path,
) -> DockerVerificationConfig:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    return DockerVerificationConfig(
        image=PINNED_IMAGE,
        runtime_root=runtime_root,
        hard_timeout_seconds=90.0,
    )


@pytest.mark.asyncio
async def test_authority_runs_fixed_pytest_in_hardened_boundary(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    launcher = RecordingLauncher()

    authority = DockerDiagnosticVerificationAuthority(
        workspace=workspace,
        config=_config(tmp_path),
        launcher=launcher,
    )

    result = await authority.verify()

    assert result.exit_code == 0
    assert result.output == "682 passed"

    assert len(launcher.commands) == 1
    command = launcher.commands[0]
    joined = " ".join(command)

    assert command[:5] == (
        "/usr/bin/docker",
        "run",
        "--rm",
        "--pull",
        "never",
    )

    assert "--network none" in joined
    assert "--read-only" in command
    assert "--cap-drop ALL" in joined
    assert "--security-opt no-new-privileges" in joined

    assert "--pids-limit 128" in joined
    assert "--memory 1g" in joined
    assert "--cpus 2" in joined
    assert "/tmp:rw,exec,nosuid,nodev,size=256m" in command

    assert (f"type=bind,src={workspace},dst=/workspace") in command

    assert (f"type=bind,src={workspace / '.git'},dst=/workspace/.git,readonly") in command

    assert "HOME=/tmp" in command
    assert "TMPDIR=/tmp" in command
    assert "XDG_CACHE_HOME=/tmp/.cache" in command
    assert "PYTHONUTF8=1" in command
    assert "PYTHONDONTWRITEBYTECODE=1" in command
    assert "PYTHONPATH=/workspace/src" in command
    assert "PIP_NO_INDEX=1" in command
    assert "PIP_FIND_LINKS=/opt/wheelhouse" in command

    assert command[-4:] == (
        "python",
        "-m",
        "pytest",
        "-q",
    )

    assert "docker.sock" not in joined
    assert "GITHUB_TOKEN" not in joined
    assert "GH_TOKEN" not in joined
    assert "MODEL_GATEWAY_API_KEY" not in joined
    assert "--privileged" not in command


@pytest.mark.asyncio
async def test_authority_uses_unique_container_name(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    launcher = RecordingLauncher()

    authority = DockerDiagnosticVerificationAuthority(
        workspace=workspace,
        config=_config(tmp_path),
        launcher=launcher,
    )

    await authority.verify()
    await authority.verify()

    names = launcher.container_names

    assert len(names) == 2
    assert len(set(names)) == 2

    assert all(name.startswith("agent-platform-diagnostic-verifier-") for name in names)


@pytest.mark.asyncio
async def test_authority_is_bound_to_one_workspace(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    launcher = RecordingLauncher()

    authority = DockerDiagnosticVerificationAuthority(
        workspace=workspace,
        config=_config(tmp_path),
        launcher=launcher,
    )

    await authority.verify()

    command = launcher.commands[0]

    mounts = [command[index + 1] for index, value in enumerate(command) if value == "--mount"]

    assert mounts == [
        (f"type=bind,src={workspace},dst=/workspace"),
        (f"type=bind,src={workspace / '.git'},dst=/workspace/.git,readonly"),
    ]


@pytest.mark.asyncio
async def test_authority_rejects_workspace_without_git_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    authority = DockerDiagnosticVerificationAuthority(
        workspace=workspace,
        config=_config(tmp_path),
        launcher=RecordingLauncher(),
    )

    with pytest.raises(
        RuntimeError,
        match=r"\.git",
    ):
        await authority.verify()
