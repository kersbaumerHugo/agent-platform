from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Protocol

from agent_platform.trust.diagnostic_verification import (
    MAX_DIAGNOSTIC_OUTPUT_CHARS,
    DiagnosticVerificationResult,
)
from agent_platform.trust.verification_docker import (
    DockerVerificationConfig,
)

_PYTEST_COMMAND = (
    "python",
    "-m",
    "pytest",
    "-q",
)

_MAX_CAPTURE_BYTES = 64 * 1024


class DockerDiagnosticVerificationError(RuntimeError):
    pass


class DiagnosticDockerLauncher(Protocol):
    async def run(
        self,
        *,
        command: tuple[str, ...],
        container_name: str,
    ) -> DiagnosticVerificationResult: ...


class DockerCliDiagnosticLauncher:
    def __init__(
        self,
        *,
        docker_binary: str,
        timeout_seconds: float,
        terminate_grace_seconds: float,
    ) -> None:
        self._docker_binary = docker_binary
        self._timeout_seconds = timeout_seconds
        self._terminate_grace_seconds = terminate_grace_seconds

    async def run(
        self,
        *,
        command: tuple[str, ...],
        container_name: str,
    ) -> DiagnosticVerificationResult:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            raise DockerDiagnosticVerificationError("Unable to start diagnostic verifier.") from exc

        assert process.stdout is not None

        reader_task = asyncio.create_task(
            self._read_bounded_output(
                process.stdout,
            )
        )

        try:
            exit_code = await asyncio.wait_for(
                process.wait(),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            await self._force_remove(
                container_name,
            )
            await self._finish_process(process)

            output = await reader_task

            return DiagnosticVerificationResult(
                exit_code=None,
                timed_out=True,
                output=output,
            )
        except asyncio.CancelledError:
            await self._force_remove(
                container_name,
            )
            await self._finish_process(process)

            if not reader_task.done():
                reader_task.cancel()

            try:
                await reader_task
            except asyncio.CancelledError:
                pass

            raise

        output = await reader_task

        if exit_code in {125, 126, 127}:
            raise DockerDiagnosticVerificationError(
                f"Diagnostic verifier container failed to start: {output}"
            )

        return DiagnosticVerificationResult(
            exit_code=exit_code,
            output=output,
        )

    @staticmethod
    async def _read_bounded_output(
        stream: asyncio.StreamReader,
    ) -> str:
        tail = bytearray()

        while True:
            chunk = await stream.read(4096)

            if not chunk:
                break

            tail.extend(chunk)

            if len(tail) > _MAX_CAPTURE_BYTES:
                del tail[:-_MAX_CAPTURE_BYTES]

        decoded = bytes(tail).decode(
            "utf-8",
            errors="replace",
        )

        return decoded[-MAX_DIAGNOSTIC_OUTPUT_CHARS:]

    async def _finish_process(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        if process.returncode is not None:
            return

        try:
            await asyncio.wait_for(
                process.wait(),
                timeout=self._terminate_grace_seconds,
            )
        except TimeoutError:
            process.kill()
            await process.wait()

    async def _force_remove(
        self,
        container_name: str,
    ) -> None:
        try:
            cleanup = await asyncio.create_subprocess_exec(
                self._docker_binary,
                "rm",
                "-f",
                container_name,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            return

        try:
            await asyncio.wait_for(
                cleanup.wait(),
                timeout=self._terminate_grace_seconds,
            )
        except TimeoutError:
            cleanup.kill()
            await cleanup.wait()


class DockerDiagnosticVerificationAuthority:
    """Run fixed diagnostic pytest outside the coding sandbox."""

    def __init__(
        self,
        *,
        workspace: Path,
        config: DockerVerificationConfig,
        launcher: DiagnosticDockerLauncher | None = None,
    ) -> None:
        self._workspace = self._resolve_workspace(workspace)
        self._config = config
        self._launcher = (
            launcher
            if launcher is not None
            else DockerCliDiagnosticLauncher(
                docker_binary=config.docker_binary,
                timeout_seconds=(config.hard_timeout_seconds),
                terminate_grace_seconds=(config.terminate_grace_seconds),
            )
        )

    async def verify(
        self,
    ) -> DiagnosticVerificationResult:
        workspace = self._workspace
        git_dir = workspace / ".git"

        if git_dir.is_symlink() or not git_dir.is_dir():
            raise DockerDiagnosticVerificationError(
                "Diagnostic verification workspace must contain a regular .git directory."
            )

        stat = workspace.stat()
        container_name = f"agent-platform-diagnostic-verifier-{uuid.uuid4().hex}"

        return await self._launcher.run(
            command=self._build_command(
                workspace=workspace,
                git_dir=git_dir,
                uid=stat.st_uid,
                gid=stat.st_gid,
                container_name=container_name,
            ),
            container_name=container_name,
        )

    def _build_command(
        self,
        *,
        workspace: Path,
        git_dir: Path,
        uid: int,
        gid: int,
        container_name: str,
    ) -> tuple[str, ...]:
        self._reject_mount_separator(workspace)
        self._reject_mount_separator(git_dir)

        workspace_mount = f"type=bind,src={workspace},dst=/workspace"
        git_mount = f"type=bind,src={git_dir},dst=/workspace/.git,readonly"

        return (
            self._config.docker_binary,
            "run",
            "--rm",
            "--pull",
            "never",
            "--name",
            container_name,
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
            git_mount,
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
            "--env",
            "PYTHONPATH=/workspace/src",
            "--env",
            "PIP_NO_INDEX=1",
            "--env",
            "PIP_FIND_LINKS=/opt/wheelhouse",
            self._config.image,
            *_PYTEST_COMMAND,
        )

    @staticmethod
    def _resolve_workspace(
        workspace: Path,
    ) -> Path:
        if workspace.is_symlink():
            raise ValueError("Diagnostic verification workspace must not be a symlink.")

        try:
            resolved = workspace.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError("Diagnostic verification workspace must exist.") from exc

        if not resolved.is_dir():
            raise ValueError("Diagnostic verification workspace must be a directory.")

        return resolved

    @staticmethod
    def _reject_mount_separator(
        path: Path,
    ) -> None:
        text = str(path)

        if "," in text or "\n" in text or "\r" in text:
            raise DockerDiagnosticVerificationError(
                "Diagnostic verification mount path contains an unsupported character."
            )
