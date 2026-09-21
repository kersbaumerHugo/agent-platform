from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agent_platform.trust.verification_executor import (
    VerificationProcessOutcome,
    VerificationProcessResult,
)

_IMAGE_REFERENCE_PATTERN = re.compile(r"^(?:.+@)?sha256:[0-9a-f]{64}$")


class DockerVerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class DockerVerificationConfig:
    image: str
    runtime_root: Path
    docker_binary: str = "/usr/bin/docker"
    hard_timeout_seconds: float = 300.0
    terminate_grace_seconds: float = 5.0
    pids_limit: int = 128
    memory_limit: str = "1g"
    cpu_limit: str = "2"
    tmpfs_spec: str = "/tmp:rw,exec,nosuid,nodev,size=256m"

    def __post_init__(self) -> None:
        if not _IMAGE_REFERENCE_PATTERN.fullmatch(self.image):
            raise ValueError("Verifier image must be pinned by sha256 digest or image ID.")

        if not self.docker_binary.strip():
            raise ValueError("docker_binary must not be empty.")

        if self.hard_timeout_seconds <= 0:
            raise ValueError("hard_timeout_seconds must be greater than zero.")

        if self.terminate_grace_seconds <= 0:
            raise ValueError("terminate_grace_seconds must be greater than zero.")

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


class DockerVerificationLauncher(Protocol):
    async def run(
        self,
        *,
        command: tuple[str, ...],
        container_name: str,
    ) -> VerificationProcessResult: ...


class DockerCliVerificationLauncher:
    """Execute one hardened verifier container and enforce lifecycle cleanup."""

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
    ) -> VerificationProcessResult:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            return VerificationProcessResult(
                outcome=VerificationProcessOutcome.ERROR,
                exit_code=None,
            )

        try:
            exit_code = await asyncio.wait_for(
                process.wait(),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            await self._force_remove(container_name)
            await self._finish_process(process)
            return VerificationProcessResult(
                outcome=VerificationProcessOutcome.TIMEOUT,
                exit_code=None,
            )
        except asyncio.CancelledError:
            await self._force_remove(container_name)
            await self._finish_process(process)
            raise

        if exit_code in {125, 126, 127}:
            return VerificationProcessResult(
                outcome=VerificationProcessOutcome.ERROR,
                exit_code=None,
            )

        return VerificationProcessResult(
            outcome=VerificationProcessOutcome.EXITED,
            exit_code=exit_code,
        )

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
            return
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


class DockerVerificationProcessRunner:
    """Run one authoritative verification step in the hardened Docker boundary."""

    def __init__(
        self,
        *,
        config: DockerVerificationConfig,
        launcher: DockerVerificationLauncher | None = None,
    ) -> None:
        self._config = config
        self._launcher = (
            launcher
            if launcher is not None
            else DockerCliVerificationLauncher(
                docker_binary=config.docker_binary,
                timeout_seconds=config.hard_timeout_seconds,
                terminate_grace_seconds=config.terminate_grace_seconds,
            )
        )

    async def run(
        self,
        *,
        workspace: Path,
        argv: tuple[str, ...],
    ) -> VerificationProcessResult:
        if not argv:
            raise ValueError("argv must not be empty.")

        if any(not part or "\x00" in part for part in argv):
            raise ValueError("argv contains an invalid argument.")

        workspace = self._resolve_workspace(workspace)
        git_dir = workspace / ".git"

        if git_dir.is_symlink() or not git_dir.is_dir():
            raise DockerVerificationError(
                "Verification workspace must contain a regular .git directory."
            )

        stat = workspace.stat()
        container_name = f"agent-platform-verifier-{uuid.uuid4().hex}"

        return await self._launcher.run(
            command=self._build_command(
                workspace=workspace,
                git_dir=git_dir,
                argv=argv,
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
        argv: tuple[str, ...],
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
            "PYTHONUTF8=1",
            "--env",
            "PYTHONPATH=/workspace/src",
            "--env",
            "PIP_NO_INDEX=1",
            "--env",
            "PIP_FIND_LINKS=/opt/wheelhouse",
            self._config.image,
            *argv,
        )

    @staticmethod
    def _resolve_workspace(
        workspace: Path,
    ) -> Path:
        if workspace.is_symlink():
            raise ValueError("Verification workspace must not be a symlink.")

        try:
            resolved = workspace.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError("Verification workspace must exist.") from exc

        if not resolved.is_dir():
            raise ValueError("Verification workspace must be a directory.")

        return resolved

    @staticmethod
    def _reject_mount_separator(
        path: Path,
    ) -> None:
        text = str(path)

        if "," in text or "\n" in text or "\r" in text:
            raise DockerVerificationError(
                "Verification mount path contains an unsupported character."
            )
