from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Callable, Mapping
from pathlib import Path

from agent_platform.worker.session import (
    WorkerExecutionRequest,
    WorkerExecutionResult,
)

CommandFactory = Callable[[Path], tuple[str, ...]]


class WorkerProcessError(RuntimeError):
    pass


class WorkerProcessTimeoutError(WorkerProcessError):
    pass


class SubprocessWorkerExecutor:
    """Run an untrusted Worker in a supervised Unix process group."""

    def __init__(
        self,
        *,
        command_factory: CommandFactory,
        timeout_seconds: float,
        terminate_grace_seconds: float = 5.0,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        if terminate_grace_seconds <= 0:
            raise ValueError("terminate_grace_seconds must be greater than zero.")

        self._command_factory = command_factory
        self._timeout_seconds = timeout_seconds
        self._terminate_grace_seconds = terminate_grace_seconds
        self._env = dict(env) if env is not None else None

    async def execute(
        self,
        request: WorkerExecutionRequest,
    ) -> WorkerExecutionResult:
        command = self._command_factory(request.workspace)

        if not command:
            raise WorkerProcessError("Worker command must not be empty.")

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=request.workspace,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._env,
            start_new_session=True,
        )

        communicate_task = asyncio.create_task(process.communicate(request.goal.encode("utf-8")))

        try:
            stdout, stderr = await asyncio.wait_for(
                asyncio.shield(communicate_task),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            await self._terminate_process_group(process)

            _, stderr = await communicate_task

            lifecycle_tail = self._safe_lifecycle_tail(stderr)

            message = "Worker execution exceeded hard timeout."

            if lifecycle_tail:
                message += "\nDSH lifecycle tail:\n" + lifecycle_tail

            raise WorkerProcessTimeoutError(message) from exc
        except asyncio.CancelledError:
            await self._terminate_process_group(process)

            await communicate_task
            raise

        if process.returncode != 0:
            detail = (
                stderr.decode(
                    "utf-8",
                    errors="replace",
                ).strip()
                or "worker process failed"
            )

            raise WorkerProcessError(f"Worker process failed: {detail}")

        return WorkerExecutionResult(
            summary=stdout.decode(
                "utf-8",
                errors="replace",
            ).strip()
        )

    @staticmethod
    def _safe_lifecycle_tail(
        stderr: bytes,
        *,
        max_lines: int = 50,
    ) -> str:
        lines = stderr.decode(
            "utf-8",
            errors="replace",
        ).splitlines()

        safe = [line for line in lines if line.startswith("DSH_LIFECYCLE ")]

        return "\n".join(safe[-max_lines:])

    async def _terminate_process_group(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        if process.returncode is not None:
            return

        try:
            os.killpg(
                process.pid,
                signal.SIGTERM,
            )
        except ProcessLookupError:
            return

        try:
            await asyncio.wait_for(
                process.wait(),
                timeout=self._terminate_grace_seconds,
            )
            return
        except TimeoutError:
            pass

        try:
            os.killpg(
                process.pid,
                signal.SIGKILL,
            )
        except ProcessLookupError:
            pass

        await process.wait()
