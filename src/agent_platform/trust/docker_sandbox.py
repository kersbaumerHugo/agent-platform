from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agent_platform.trust.diagnostic_verification import (
    TrustedDiagnosticVerificationHandler,
    UnixSocketDiagnosticVerificationServer,
)
from agent_platform.trust.diagnostic_verification_docker import (
    DockerDiagnosticVerificationAuthority,
)
from agent_platform.trust.sandbox_execution import (
    SandboxExecutionRequest,
)
from agent_platform.trust.sandbox_gateway_relay import (
    UnixSocketGatewayCredentialRelay,
)
from agent_platform.trust.sandbox_service import (
    SandboxExecutionOutcome,
)
from agent_platform.trust.verification_docker import (
    DockerVerificationConfig,
)


class DockerSandboxError(RuntimeError):
    pass


class DockerSandboxTimeoutError(DockerSandboxError):
    pass


_IMAGE_REFERENCE_PATTERN = re.compile(r"^(?:.+@)?sha256:[0-9a-f]{64}$")

_DIAGNOSTIC_VERIFIER_CONTAINER_SOCKET = Path("/run/diagnostic-verifier.sock")
_DIAGNOSTIC_VERIFICATION_TIMEOUT_SECONDS = 90.0


@dataclass(frozen=True)
class DockerSandboxConfig:
    image: str
    command: tuple[str, ...]
    runtime_root: Path
    gateway_upstream_host: str
    gateway_upstream_port: int
    gateway_api_key: str
    docker_binary: str = "/usr/bin/docker"
    hard_timeout_seconds: float = 300.0
    # Worker sandboxes run orchestration, model runtime and verification
    # processes together. 96 caused PID pressure during self-verification.
    pids_limit: int = 160
    memory_limit: str = "256m"
    cpu_limit: str = "1"
    tmpfs_spec: str = "/tmp:rw,exec,nosuid,nodev,size=16m"

    def __post_init__(self) -> None:
        if not _IMAGE_REFERENCE_PATTERN.fullmatch(self.image):
            raise ValueError("Sandbox image must be pinned by sha256 digest or image ID.")

        if not self.command:
            raise ValueError("Sandbox command must not be empty.")

        if any(not part or "\x00" in part for part in self.command):
            raise ValueError("Sandbox command contains an invalid argument.")

        if not self.gateway_upstream_host.strip():
            raise ValueError("gateway_upstream_host must not be empty.")

        if not 1 <= self.gateway_upstream_port <= 65535:
            raise ValueError("gateway_upstream_port must be between 1 and 65535.")

        if not self.gateway_api_key:
            raise ValueError("gateway_api_key must not be empty.")

        if not self.docker_binary.strip():
            raise ValueError("docker_binary must not be empty.")

        if self.hard_timeout_seconds <= 0:
            raise ValueError("hard_timeout_seconds must be greater than zero.")

        if self.pids_limit <= 0:
            raise ValueError("pids_limit must be greater than zero.")

        runtime_root = self.runtime_root

        if runtime_root.is_symlink():
            raise ValueError("runtime_root must not be a symlink.")

        try:
            resolved_root = runtime_root.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError("runtime_root must exist.") from exc

        if not resolved_root.is_dir():
            raise ValueError("runtime_root must be a directory.")

        object.__setattr__(
            self,
            "runtime_root",
            resolved_root,
        )


@dataclass(frozen=True)
class DockerExecution:
    command: tuple[str, ...]
    stdin: bytes
    container_name: str


class DockerExecutionRunner(Protocol):
    async def run(
        self,
        execution: DockerExecution,
    ) -> str: ...


class SubprocessDockerExecutionRunner:
    """Run one fixed Docker CLI invocation with hard-timeout cleanup."""

    def __init__(
        self,
        *,
        docker_binary: str,
        timeout_seconds: float,
        terminate_grace_seconds: float = 5.0,
    ) -> None:
        if not docker_binary.strip():
            raise ValueError("docker_binary must not be empty.")

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        if terminate_grace_seconds <= 0:
            raise ValueError("terminate_grace_seconds must be greater than zero.")

        self._docker_binary = docker_binary
        self._timeout_seconds = timeout_seconds
        self._terminate_grace_seconds = terminate_grace_seconds

    async def run(
        self,
        execution: DockerExecution,
    ) -> str:
        process = await asyncio.create_subprocess_exec(
            *execution.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        communicate_task = asyncio.create_task(process.communicate(execution.stdin))

        try:
            stdout, stderr = await asyncio.wait_for(
                asyncio.shield(communicate_task),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            await self._force_remove(execution.container_name)
            await self._finish_process(
                process,
                communicate_task,
            )

            raise DockerSandboxTimeoutError("Sandbox execution exceeded hard timeout.") from exc
        except asyncio.CancelledError:
            await self._force_remove(execution.container_name)
            await self._finish_process(
                process,
                communicate_task,
            )
            raise

        if process.returncode != 0:
            detail = stderr.decode(
                "utf-8",
                errors="replace",
            ).strip()

            if not detail:
                detail = "sandbox container failed"

            raise DockerSandboxError(f"Sandbox container failed: {detail}")

        self._forward_lifecycle(stderr)

        return stdout.decode(
            "utf-8",
            errors="replace",
        ).strip()

    @staticmethod
    def _forward_lifecycle(stderr: bytes) -> None:
        lines = stderr.decode(
            "utf-8",
            errors="replace",
        ).splitlines()

        lifecycle_lines = [line for line in lines if line.startswith("DSH_LIFECYCLE ")]

        if not lifecycle_lines:
            return

        sys.stderr.write("\n".join(lifecycle_lines) + "\n")
        sys.stderr.flush()

    async def _finish_process(
        self,
        process: asyncio.subprocess.Process,
        communicate_task: asyncio.Task[tuple[bytes, bytes]],
    ) -> None:
        try:
            await asyncio.wait_for(
                asyncio.shield(communicate_task),
                timeout=self._terminate_grace_seconds,
            )
        except TimeoutError:
            process.kill()
            await process.wait()

            if not communicate_task.done():
                communicate_task.cancel()

            try:
                await communicate_task
            except asyncio.CancelledError:
                pass

    async def _force_remove(
        self,
        container_name: str,
    ) -> None:
        cleanup = await asyncio.create_subprocess_exec(
            self._docker_binary,
            "rm",
            "-f",
            container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        try:
            await asyncio.wait_for(
                cleanup.wait(),
                timeout=self._terminate_grace_seconds,
            )
        except TimeoutError:
            cleanup.kill()
            await cleanup.wait()


class DockerSandboxBackend:
    """Execute coding work behind the fixed M12 V0 Docker boundary."""

    def __init__(
        self,
        *,
        config: DockerSandboxConfig,
        runner: DockerExecutionRunner | None = None,
    ) -> None:
        self._config = config
        self._runner = (
            runner
            if runner is not None
            else SubprocessDockerExecutionRunner(
                docker_binary=config.docker_binary,
                timeout_seconds=(config.hard_timeout_seconds),
            )
        )

    async def execute(
        self,
        request: SandboxExecutionRequest,
        *,
        workspace: Path,
    ) -> SandboxExecutionOutcome:
        workspace = workspace.resolve(strict=True)

        if not workspace.is_dir():
            raise DockerSandboxError("Sandbox workspace must be a directory.")

        stat = workspace.stat()
        uid = stat.st_uid
        gid = stat.st_gid

        socket_path = self._gateway_socket_path(request)
        diagnostic_socket_path = self._diagnostic_socket_path(request)

        relay = UnixSocketGatewayCredentialRelay(
            socket_path=socket_path,
            upstream_host=(self._config.gateway_upstream_host),
            upstream_port=(self._config.gateway_upstream_port),
            gateway_api_key=(self._config.gateway_api_key),
            socket_mode=0o660,
        )

        diagnostic_authority = DockerDiagnosticVerificationAuthority(
            workspace=workspace,
            config=DockerVerificationConfig(
                image=self._config.image,
                runtime_root=self._config.runtime_root,
                docker_binary=self._config.docker_binary,
                hard_timeout_seconds=(_DIAGNOSTIC_VERIFICATION_TIMEOUT_SECONDS),
            ),
        )

        diagnostic_handler = TrustedDiagnosticVerificationHandler(
            authority=diagnostic_authority,
            max_requests=2,
        )

        diagnostic_server = UnixSocketDiagnosticVerificationServer(
            socket_path=diagnostic_socket_path,
            handler=diagnostic_handler,
        )

        try:
            await relay.start()
            await diagnostic_server.start()

            os.chown(
                socket_path,
                uid,
                gid,
            )

            os.chown(
                diagnostic_socket_path,
                uid,
                gid,
            )

            execution = DockerExecution(
                command=self._build_command(
                    request=request,
                    workspace=workspace,
                    socket_path=socket_path,
                    diagnostic_socket_path=(diagnostic_socket_path),
                    uid=uid,
                    gid=gid,
                ),
                stdin=request.goal.encode("utf-8"),
                container_name=self._container_name(request),
            )

            summary = await self._runner.run(execution)

            return SandboxExecutionOutcome(summary=summary)
        finally:
            await diagnostic_server.close()
            await relay.close()

    def _build_command(
        self,
        *,
        request: SandboxExecutionRequest,
        workspace: Path,
        socket_path: Path,
        diagnostic_socket_path: Path,
        uid: int,
        gid: int,
    ) -> tuple[str, ...]:
        self._reject_mount_separator(workspace)
        self._reject_mount_separator(socket_path)
        self._reject_mount_separator(diagnostic_socket_path)

        workspace_mount = f"type=bind,src={workspace},dst=/workspace"
        gateway_mount = f"type=bind,src={socket_path},dst=/run/model-gateway.sock,readonly"
        diagnostic_mount = (
            f"type=bind,src={diagnostic_socket_path},"
            f"dst={_DIAGNOSTIC_VERIFIER_CONTAINER_SOCKET},"
            "readonly"
        )

        return (
            self._config.docker_binary,
            "run",
            "--rm",
            "-i",
            "--name",
            self._container_name(request),
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(self._config.pids_limit),
            "--memory",
            self._config.memory_limit,
            "--cpus",
            self._config.cpu_limit,
            "--user",
            f"{uid}:{gid}",
            "--tmpfs",
            self._config.tmpfs_spec,
            "--workdir",
            "/workspace",
            "--mount",
            workspace_mount,
            "--mount",
            gateway_mount,
            "--mount",
            diagnostic_mount,
            "--env",
            ("DEEPSEEK_BASE_URL=http://127.0.0.1:18080/internal/v1"),
            "--env",
            ("DEEPSEEK_API_KEY=sandbox-relay-placeholder"),
            "--env",
            ("AGENT_PLATFORM_GATEWAY_SOCKET=/run/model-gateway.sock"),
            "--env",
            (f"AGENT_PLATFORM_DIAGNOSTIC_VERIFIER_SOCKET={_DIAGNOSTIC_VERIFIER_CONTAINER_SOCKET}"),
            "--env",
            "HOME=/tmp",
            "--env",
            "TMPDIR=/tmp",
            "--env",
            "XDG_CACHE_HOME=/tmp/.cache",
            "--env",
            "PYTHONUTF8=1",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            self._config.image,
            *self._config.command,
        )

    def _gateway_socket_path(
        self,
        request: SandboxExecutionRequest,
    ) -> Path:
        return self._config.runtime_root / (f"gw-{request.execution_id.hex[:16]}.sock")

    def _diagnostic_socket_path(
        self,
        request: SandboxExecutionRequest,
    ) -> Path:
        return self._config.runtime_root / (f"dv-{request.execution_id.hex[:16]}.sock")

    @staticmethod
    def _container_name(
        request: SandboxExecutionRequest,
    ) -> str:
        return f"agent-platform-coding-{request.execution_id.hex}"

    @staticmethod
    def _reject_mount_separator(
        path: Path,
    ) -> None:
        text = str(path)

        if "," in text or "\n" in text or "\r" in text:
            raise DockerSandboxError("Sandbox mount path contains an unsupported character.")
