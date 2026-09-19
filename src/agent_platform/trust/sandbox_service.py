from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from agent_platform.trust.sandbox_execution import (
    SandboxExecutionRequest,
    SandboxExecutionRequestError,
    SandboxExecutionResponse,
    SandboxExecutionStatus,
    TrustedWorkspaceError,
    TrustedWorkspaceResolver,
    deserialize_sandbox_execution_request,
    serialize_sandbox_execution_response,
)

MAX_SANDBOX_REQUEST_BYTES = 1024 * 1024


@dataclass(frozen=True)
class SandboxExecutionOutcome:
    summary: str


class SandboxExecutionBackend(Protocol):
    async def execute(
        self,
        request: SandboxExecutionRequest,
        *,
        workspace: Path,
    ) -> SandboxExecutionOutcome: ...


class TrustedSandboxExecutionHandler:
    """Validate a narrow request before crossing into Docker authority."""

    def __init__(
        self,
        *,
        workspace_resolver: TrustedWorkspaceResolver,
        backend: SandboxExecutionBackend,
    ) -> None:
        self._workspace_resolver = workspace_resolver
        self._backend = backend
        self._execution_lock = asyncio.Lock()

    async def handle(
        self,
        raw_request: str,
    ) -> SandboxExecutionResponse:
        try:
            request = deserialize_sandbox_execution_request(raw_request)
        except SandboxExecutionRequestError:
            return self._error(
                execution_id=None,
                error_code="invalid_sandbox_request",
            )

        try:
            workspace = self._workspace_resolver.resolve(request.workspace_name)
        except TrustedWorkspaceError:
            return self._error(
                execution_id=request.execution_id,
                error_code="invalid_workspace",
            )

        try:
            async with self._execution_lock:
                outcome = await self._backend.execute(
                    request,
                    workspace=workspace,
                )

            return SandboxExecutionResponse(
                status=SandboxExecutionStatus.ACCEPTED,
                execution_id=request.execution_id,
                summary=outcome.summary,
            )
        except Exception:
            return self._error(
                execution_id=request.execution_id,
                error_code="execution_failed",
            )

    @staticmethod
    def _error(
        *,
        execution_id: UUID | None,
        error_code: str,
    ) -> SandboxExecutionResponse:
        return SandboxExecutionResponse(
            status=SandboxExecutionStatus.ERROR,
            execution_id=execution_id,
            error_code=error_code,
        )


class UnixSocketSandboxServer:
    def __init__(
        self,
        *,
        socket_path: Path,
        handler: TrustedSandboxExecutionHandler,
    ) -> None:
        self._socket_path = socket_path
        self._handler = handler
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("Sandbox server is already started.")

        if self._socket_path.exists():
            raise RuntimeError("Sandbox socket path already exists.")

        self._socket_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=self._socket_path,
            limit=MAX_SANDBOX_REQUEST_BYTES + 1,
        )

    async def close(self) -> None:
        if self._server is None:
            return

        self._server.close()
        await self._server.wait_closed()
        self._server = None

        try:
            self._socket_path.unlink()
        except FileNotFoundError:
            pass

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            try:
                raw = await reader.readline()
            except (
                asyncio.LimitOverrunError,
                ValueError,
            ):
                response = SandboxExecutionResponse(
                    status=SandboxExecutionStatus.ERROR,
                    execution_id=None,
                    error_code="invalid_transport_request",
                )
            else:
                if not raw or len(raw) > MAX_SANDBOX_REQUEST_BYTES or not raw.endswith(b"\n"):
                    response = SandboxExecutionResponse(
                        status=SandboxExecutionStatus.ERROR,
                        execution_id=None,
                        error_code="invalid_transport_request",
                    )
                else:
                    try:
                        decoded = raw[:-1].decode("utf-8")
                    except UnicodeDecodeError:
                        response = SandboxExecutionResponse(
                            status=SandboxExecutionStatus.ERROR,
                            execution_id=None,
                            error_code="invalid_encoding",
                        )
                    else:
                        response = await self._handler.handle(decoded)

            writer.write(serialize_sandbox_execution_response(response).encode("utf-8") + b"\n")
            await writer.drain()
        finally:
            writer.close()

            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
