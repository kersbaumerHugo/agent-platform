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
        context_window=8192,
        max_output_tokens=1536,
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

    profile_index = command.index("--profile")
    assert command[profile_index + 1] == "sdk-minimal"

    context_window_index = command.index("--context-window")
    assert command[context_window_index + 1] == "8192"

    max_output_tokens_index = command.index("--max-output-tokens")
    assert command[max_output_tokens_index + 1] == "1536"

    assert backend._config.tmpfs_spec == ("/tmp:rw,exec,nosuid,nodev,size=64m")

    assert "trusted-secret" not in command
