from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

import pytest

from agent_platform.trust.docker_sandbox import (
    DockerExecution,
    DockerSandboxBackend,
    DockerSandboxConfig,
    SubprocessDockerExecutionRunner,
)
from agent_platform.trust.sandbox_execution import (
    SandboxExecutionMode,
    SandboxExecutionRequest,
)

EXECUTION_ID = UUID("2d4cf0d5-59f0-4cd5-9d46-612b35f9598d")

PINNED_IMAGE = "agent-platform-coding@sha256:" + ("a" * 64)


def contains_all(
    command: Sequence[str],
    expected: Sequence[str],
) -> bool:
    if not expected:
        return True

    width = len(expected)

    return any(
        tuple(command[index : index + width]) == tuple(expected)
        for index in range(len(command) - width + 1)
    )


class RecordingRunner:
    def __init__(self) -> None:
        self.executions: list[DockerExecution] = []

    async def run(
        self,
        execution: DockerExecution,
    ) -> str:
        self.executions.append(execution)

        return "sandbox complete"


def build_config(
    runtime_root: Path,
) -> DockerSandboxConfig:
    return DockerSandboxConfig(
        image=PINNED_IMAGE,
        command=(
            "python",
            "-m",
            "agent_platform.worker.sandbox_process",
        ),
        runtime_root=runtime_root,
        gateway_upstream_host="127.0.0.1",
        gateway_upstream_port=8000,
        gateway_api_key=("trusted-gateway-secret"),
    )


def request() -> SandboxExecutionRequest:
    return SandboxExecutionRequest(
        execution_id=EXECUTION_ID,
        workspace_name="worker-example",
        goal="Fix the requested test.",
    )


@pytest.mark.asyncio
async def test_backend_builds_fixed_hardened_command(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    runner = RecordingRunner()

    backend = DockerSandboxBackend(
        config=build_config(runtime_root),
        runner=runner,
    )

    result = await backend.execute(
        request(),
        workspace=workspace,
    )

    assert result.summary == "sandbox complete"
    assert len(runner.executions) == 1

    execution = runner.executions[0]
    command = execution.command

    assert contains_all(
        command,
        ("--network", "none"),
    )
    assert "--read-only" in command
    assert contains_all(
        command,
        ("--cap-drop", "ALL"),
    )
    assert contains_all(
        command,
        (
            "--security-opt",
            "no-new-privileges",
        ),
    )
    assert contains_all(
        command,
        ("--pids-limit", "160"),
    )
    assert contains_all(
        command,
        ("--memory", "256m"),
    )
    assert contains_all(
        command,
        ("--cpus", "1"),
    )
    assert contains_all(
        command,
        ("--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=16m"),
    )

    assert contains_all(
        command,
        (
            "--env",
            ("DEEPSEEK_API_KEY=sandbox-relay-placeholder"),
        ),
    )
    assert "trusted-gateway-secret" not in command

    assert contains_all(
        command,
        (
            "--env",
            ("AGENT_PLATFORM_DIAGNOSTIC_VERIFIER_SOCKET=/run/diagnostic-verifier.sock"),
        ),
    )

    assert contains_all(
        command,
        ("--env", "HOME=/tmp"),
    )
    assert contains_all(
        command,
        ("--env", "TMPDIR=/tmp"),
    )
    assert contains_all(
        command,
        ("--env", "XDG_CACHE_HOME=/tmp/.cache"),
    )
    assert contains_all(
        command,
        ("--env", "PYTHONUTF8=1"),
    )
    assert contains_all(
        command,
        ("--env", "PYTHONDONTWRITEBYTECODE=1"),
    )

    serialized = " ".join(command)

    assert "/var/run/docker.sock" not in serialized
    assert "trusted-change.sock" not in serialized

    mounts = [command[index + 1] for index, token in enumerate(command[:-1]) if token == "--mount"]

    assert len(mounts) == 3
    assert any("dst=/workspace" in mount and ",readonly" not in mount for mount in mounts)
    assert any("dst=/run/model-gateway.sock,readonly" in mount for mount in mounts)
    assert any(("dst=/run/diagnostic-verifier.sock,readonly") in mount for mount in mounts)

    assert contains_all(
        command,
        ("--mode", "implementation"),
    )
    assert execution.stdin == (b"Fix the requested test.")
    assert execution.container_name == ("agent-platform-coding-2d4cf0d559f04cd59d46612b35f9598d")

    assert list(runtime_root.iterdir()) == []


def test_config_requires_digest_pinned_image(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    with pytest.raises(
        ValueError,
        match="pinned",
    ):
        DockerSandboxConfig(
            image="python:3.12-slim",
            command=("python",),
            runtime_root=runtime_root,
            gateway_upstream_host=("127.0.0.1"),
            gateway_upstream_port=8000,
            gateway_api_key="secret",
        )


def test_config_rejects_symlink_runtime_root(
    tmp_path: Path,
) -> None:
    real_root = tmp_path / "real-runtime"
    real_root.mkdir()

    linked_root = tmp_path / "runtime"
    linked_root.symlink_to(
        real_root,
        target_is_directory=True,
    )

    with pytest.raises(
        ValueError,
        match="symlink",
    ):
        build_config(linked_root)


@pytest.mark.asyncio
async def test_goal_does_not_change_docker_authority(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    runner = RecordingRunner()
    backend = DockerSandboxBackend(
        config=build_config(runtime_root),
        runner=runner,
    )

    hostile_goal = "--privileged --network host -v /:/host --user root docker.sock"

    hostile_request = SandboxExecutionRequest(
        execution_id=EXECUTION_ID,
        workspace_name=("worker-example"),
        goal=hostile_goal,
    )

    await backend.execute(
        hostile_request,
        workspace=workspace,
    )

    execution = runner.executions[0]
    command = execution.command

    assert hostile_goal not in command
    assert execution.stdin == (hostile_goal.encode("utf-8"))
    assert "--privileged" not in command
    assert contains_all(
        command,
        ("--network", "none"),
    )
    assert "host" not in command


def test_mount_paths_reject_docker_mount_separator(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    workspace = tmp_path / "bad,workspace"
    workspace.mkdir()

    backend = DockerSandboxBackend(
        config=build_config(runtime_root),
        runner=RecordingRunner(),
    )

    with pytest.raises(
        RuntimeError,
        match="unsupported character",
    ):
        backend._build_command(
            request=request(),
            workspace=workspace,
            socket_path=runtime_root / "gateway.sock",
            diagnostic_socket_path=(runtime_root / "diagnostic.sock"),
            uid=1000,
            gid=1000,
        )


def test_gateway_socket_path_stays_short_for_long_runtime_root(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    backend = DockerSandboxBackend(
        config=build_config(runtime_root),
        runner=RecordingRunner(),
    )

    socket_path = backend._gateway_socket_path(request())

    assert socket_path.parent == runtime_root.resolve()
    assert socket_path.name == ("gw-2d4cf0d559f04cd5.sock")
    assert len(str(socket_path).encode("utf-8")) < 108


def test_diagnostic_socket_path_stays_short(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    backend = DockerSandboxBackend(
        config=build_config(runtime_root),
        runner=RecordingRunner(),
    )

    socket_path = backend._diagnostic_socket_path(request())

    assert socket_path.parent == (runtime_root.resolve())
    assert socket_path.name == ("dv-2d4cf0d559f04cd5.sock")
    assert len(str(socket_path).encode("utf-8")) < 108


def test_docker_runner_forwards_only_dsh_lifecycle_stderr(
    capsys,
) -> None:
    SubprocessDockerExecutionRunner._forward_lifecycle(
        b"ordinary stderr that must stay hidden\n"
        b'DSH_LIFECYCLE {"method":"session.event","event_type":"tool/call"}\n'
        b"secret worker output\n"
    )

    captured = capsys.readouterr()

    assert "DSH_LIFECYCLE" in captured.err
    assert '"event_type":"tool/call"' in captured.err

    assert "ordinary stderr" not in captured.err
    assert "secret worker output" not in captured.err


def test_backend_passes_semantic_review_mode_to_fixed_process(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime-semantic"
    runtime_root.mkdir()

    workspace = tmp_path / "workspace-semantic"
    workspace.mkdir()

    backend = DockerSandboxBackend(
        config=build_config(runtime_root),
        runner=RecordingRunner(),
    )

    semantic_request = SandboxExecutionRequest(
        execution_id=EXECUTION_ID,
        workspace_name="worker-example",
        goal="Review only.",
        mode=SandboxExecutionMode.SEMANTIC_REVIEW,
    )

    command = backend._build_command(
        request=semantic_request,
        workspace=workspace,
        socket_path=runtime_root / "gw.sock",
        diagnostic_socket_path=runtime_root / "dv.sock",
        uid=1000,
        gid=1000,
    )

    assert contains_all(
        command,
        ("--mode", "semantic_review"),
    )
