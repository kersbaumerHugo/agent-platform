from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

from agent_platform.worker.session import (
    WorkerExecutionRequest,
    WorkerExecutionResult,
)
from agent_platform.worker.supervisor import (
    SubprocessWorkerExecutor,
)


class DshSubprocessWorkerExecutor:
    """Run the DSH Worker behind a hard subprocess boundary."""

    def __init__(
        self,
        *,
        dsh_home: Path,
        provider: str,
        model: str,
        env: Mapping[str, str],
        profile: str = "sdk",
        request_timeout_seconds: float | None = 120.0,
        hard_timeout_seconds: float = 300.0,
        terminate_grace_seconds: float = 5.0,
    ) -> None:
        if not provider.strip():
            raise ValueError("provider must not be empty.")

        if not model.strip():
            raise ValueError("model must not be empty.")

        if not profile.strip():
            raise ValueError("profile must not be empty.")

        if request_timeout_seconds is not None and request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be greater than zero.")

        process_env = dict(env)

        if not process_env.get("PATH", "").strip():
            raise ValueError("Worker subprocess environment must include PATH.")

        process_env["AGENT_PLATFORM_DSH_HOME"] = str(dsh_home.resolve())

        process_env["AGENT_PLATFORM_DSH_PROVIDER"] = provider

        process_env["AGENT_PLATFORM_DSH_MODEL"] = model

        process_env["AGENT_PLATFORM_DSH_PROFILE"] = profile

        process_env["AGENT_PLATFORM_DSH_REQUEST_TIMEOUT_SECONDS"] = (
            "none" if request_timeout_seconds is None else str(request_timeout_seconds)
        )

        self._delegate = SubprocessWorkerExecutor(
            command_factory=self._command,
            timeout_seconds=hard_timeout_seconds,
            terminate_grace_seconds=(terminate_grace_seconds),
            env=process_env,
        )

    async def execute(
        self,
        request: WorkerExecutionRequest,
    ) -> WorkerExecutionResult:
        return await self._delegate.execute(request)

    @staticmethod
    def _command(
        workspace: Path,
    ) -> tuple[str, ...]:
        del workspace

        return (
            sys.executable,
            "-m",
            "agent_platform.worker.dsh_process",
        )
