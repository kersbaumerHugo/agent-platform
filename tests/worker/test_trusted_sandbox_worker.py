from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from agent_platform.adapters.workers.trusted_sandbox import (
    TrustedSandboxWorkerError,
    TrustedSandboxWorkerExecutor,
)
from agent_platform.trust.sandbox_execution import (
    SandboxExecutionResponse,
    SandboxExecutionStatus,
    TrustedWorkspaceResolver,
    deserialize_sandbox_execution_request,
    serialize_sandbox_execution_response,
)
from agent_platform.trust.sandbox_service import (
    SandboxExecutionOutcome,
    TrustedSandboxExecutionHandler,
    UnixSocketSandboxServer,
)
from agent_platform.worker.session import (
    WorkerExecutionRequest,
)

EXECUTION_ID = UUID("12000000-0000-4000-8000-000000000009")


@pytest.mark.asyncio
async def test_client_and_server_cross_narrow_socket_boundary(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    workspace = root / "worker-example"
    workspace.mkdir()

    calls: list[tuple[UUID, str, Path]] = []

    class Backend:
        async def execute(
            self,
            request,
            *,
            workspace: Path,
        ) -> SandboxExecutionOutcome:
            calls.append(
                (
                    request.execution_id,
                    request.goal,
                    workspace,
                )
            )

            return SandboxExecutionOutcome(
                summary="trusted sandbox completed",
            )

    socket_path = tmp_path / "sandbox.sock"

    server = UnixSocketSandboxServer(
        socket_path=socket_path,
        handler=TrustedSandboxExecutionHandler(
            workspace_resolver=TrustedWorkspaceResolver(workspace_root=root),
            backend=Backend(),
        ),
    )

    await server.start()

    try:
        client = TrustedSandboxWorkerExecutor(
            socket_path=socket_path,
            workspace_root=root,
        )

        result = await client.execute(
            WorkerExecutionRequest(
                goal="Fix the test.",
                workspace=workspace,
                execution_id=EXECUTION_ID,
            )
        )
    finally:
        await server.close()

    assert result.summary == ("trusted sandbox completed")
    assert calls == [
        (
            EXECUTION_ID,
            "Fix the test.",
            workspace.resolve(),
        )
    ]
    assert not socket_path.exists()


@pytest.mark.asyncio
async def test_client_rejects_workspace_outside_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()

    client = TrustedSandboxWorkerExecutor(
        socket_path=tmp_path / "missing.sock",
        workspace_root=root,
    )

    with pytest.raises(
        TrustedSandboxWorkerError,
        match="outside",
    ):
        await client.execute(
            WorkerExecutionRequest(
                goal="Fix the test.",
                workspace=outside,
            )
        )


@pytest.mark.asyncio
async def test_client_rejects_response_execution_id_mismatch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    workspace = root / "worker-example"
    workspace.mkdir()

    socket_path = tmp_path / "sandbox.sock"

    async def handler(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        raw = await reader.readline()

        request = deserialize_sandbox_execution_request(raw.decode("utf-8").strip())

        wrong_id = uuid4()

        assert wrong_id != request.execution_id

        response = SandboxExecutionResponse(
            status=SandboxExecutionStatus.ACCEPTED,
            execution_id=wrong_id,
            summary="wrong execution",
        )

        writer.write(serialize_sandbox_execution_response(response).encode("utf-8") + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(
        handler,
        path=socket_path,
    )

    try:
        client = TrustedSandboxWorkerExecutor(
            socket_path=socket_path,
            workspace_root=root,
        )

        with pytest.raises(
            TrustedSandboxWorkerError,
            match="execution_id mismatch",
        ):
            await client.execute(
                WorkerExecutionRequest(
                    goal="Fix the test.",
                    workspace=workspace,
                )
            )
    finally:
        server.close()
        await server.wait_closed()
