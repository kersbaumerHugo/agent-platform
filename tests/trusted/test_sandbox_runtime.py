from pathlib import Path

from agent_platform.trust.docker_sandbox import (
    DockerSandboxBackend,
)
from agent_platform.trust.sandbox_runtime import build_server

IMAGE = "agent-platform-coding@sha256:" + ("a" * 64)


def test_builds_trusted_dsh_sandbox_without_secret_in_command(
    tmp_path: Path,
) -> None:
    workspaces = tmp_path / "workspaces"
    runtime = tmp_path / "runtime"

    workspaces.mkdir()
    runtime.mkdir()

    server = build_server(
        socket_path=tmp_path / "sandbox.sock",
        workspace_root=workspaces,
        runtime_root=runtime,
        image=IMAGE,
        gateway_host="127.0.0.1",
        gateway_port=8000,
        gateway_api_key="trusted-secret",
        provider="test-provider",
        model="test-model",
    )

    backend = server._handler._backend

    assert isinstance(
        backend,
        DockerSandboxBackend,
    )

    command = backend._config.command

    assert command[:3] == (
        "python",
        "-m",
        "agent_platform.worker.sandbox_process",
    )

    assert "--provider" in command
    assert "test-provider" in command
    assert "--model" in command
    assert "test-model" in command

    assert "trusted-secret" not in command
