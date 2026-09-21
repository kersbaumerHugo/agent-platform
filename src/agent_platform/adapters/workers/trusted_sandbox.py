from __future__ import annotations

import asyncio
from pathlib import Path

from agent_platform.trust.sandbox_execution import (
    SandboxExecutionRequest,
    SandboxExecutionResponseError,
    SandboxExecutionStatus,
    TrustedWorkspaceError,
    TrustedWorkspaceResolver,
    deserialize_sandbox_execution_response,
    serialize_sandbox_execution_request,
)
from agent_platform.worker.session import (
    WorkerExecutionRequest,
    WorkerExecutionResult,
)


class TrustedSandboxWorkerError(RuntimeError):
    pass


class TrustedSandboxWorkerExecutor:
    """Submit one Worker execution to the trusted sandbox boundary."""

    def __init__(
        self,
        *,
        socket_path: Path,
        workspace_root: Path,
        max_response_bytes: int = 64 * 1024,
    ) -> None:
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be greater than zero.")

        self._socket_path = socket_path
        self._workspace_resolver = TrustedWorkspaceResolver(workspace_root=workspace_root)
        self._max_response_bytes = max_response_bytes

    async def execute(
        self,
        request: WorkerExecutionRequest,
    ) -> WorkerExecutionResult:
        workspace_name = self._workspace_name(request.workspace)

        sandbox_request = SandboxExecutionRequest(
            execution_id=request.execution_id,
            workspace_name=workspace_name,
            goal=request.goal,
        )

        try:
            reader, writer = await asyncio.open_unix_connection(
                self._socket_path,
                limit=self._max_response_bytes + 1,
            )
        except OSError as exc:
            raise TrustedSandboxWorkerError(
                "Unable to connect to trusted sandbox executor."
            ) from exc

        try:
            writer.write(
                serialize_sandbox_execution_request(sandbox_request).encode("utf-8") + b"\n"
            )
            await writer.drain()

            try:
                raw_response = await reader.readline()
            except (
                asyncio.LimitOverrunError,
                ValueError,
            ) as exc:
                raise TrustedSandboxWorkerError(
                    "Trusted sandbox response exceeded protocol limit."
                ) from exc

            if not raw_response:
                raise TrustedSandboxWorkerError("Trusted sandbox executor returned no response.")

            if len(raw_response) > self._max_response_bytes:
                raise TrustedSandboxWorkerError("Trusted sandbox response exceeded protocol limit.")

            if not raw_response.endswith(b"\n"):
                raise TrustedSandboxWorkerError(
                    "Trusted sandbox executor returned an incomplete response."
                )

            try:
                decoded = raw_response[:-1].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise TrustedSandboxWorkerError(
                    "Trusted sandbox executor returned invalid encoding."
                ) from exc

            try:
                response = deserialize_sandbox_execution_response(decoded)
            except SandboxExecutionResponseError as exc:
                raise TrustedSandboxWorkerError(
                    "Trusted sandbox executor returned invalid response."
                ) from exc

            if response.execution_id is not None and response.execution_id != request.execution_id:
                raise TrustedSandboxWorkerError("Trusted sandbox response execution_id mismatch.")

            if response.status is SandboxExecutionStatus.ERROR:
                raise TrustedSandboxWorkerError(
                    f"Trusted sandbox execution failed: {response.error_code}"
                )

            if response.execution_id != request.execution_id:
                raise TrustedSandboxWorkerError(
                    "Trusted sandbox accepted response without matching execution_id."
                )

            return WorkerExecutionResult(summary=response.summary or "")
        finally:
            writer.close()

            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    def _workspace_name(
        self,
        workspace: Path,
    ) -> str:
        try:
            resolved = self._workspace_resolver.resolve(workspace.name)
        except TrustedWorkspaceError as exc:
            raise TrustedSandboxWorkerError(
                "Worker workspace is outside the trusted workspace root."
            ) from exc

        try:
            requested = workspace.resolve(strict=True)
        except FileNotFoundError as exc:
            raise TrustedSandboxWorkerError("Worker workspace does not exist.") from exc

        if requested != resolved:
            raise TrustedSandboxWorkerError(
                "Worker workspace is outside the trusted workspace root."
            )

        return resolved.name
