from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from agent_platform.trust.sandbox_execution import (
    SandboxExecutionRequest,
    SandboxExecutionStatus,
    TrustedWorkspaceResolver,
    deserialize_sandbox_execution_response,
    serialize_sandbox_execution_request,
)
from agent_platform.trust.sandbox_service import (
    SandboxExecutionOutcome,
    TrustedSandboxExecutionHandler,
)

EXECUTION_ID = UUID("afc5693b-d9b5-4a53-907e-b542aecc24ec")


class RecordingBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[SandboxExecutionRequest, Path]] = []

    async def execute(
        self,
        request: SandboxExecutionRequest,
        *,
        workspace: Path,
    ) -> SandboxExecutionOutcome:
        self.calls.append(
            (
                request,
                workspace,
            )
        )

        return SandboxExecutionOutcome(
            summary="sandbox completed",
        )


def build_handler(
    *,
    root: Path,
    backend: RecordingBackend,
) -> TrustedSandboxExecutionHandler:
    return TrustedSandboxExecutionHandler(
        workspace_resolver=TrustedWorkspaceResolver(workspace_root=root),
        backend=backend,
    )


@pytest.mark.asyncio
async def test_handler_resolves_workspace_before_backend(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    workspace = root / "worker-example"
    workspace.mkdir()

    backend = RecordingBackend()
    handler = build_handler(
        root=root,
        backend=backend,
    )

    response = await handler.handle(
        serialize_sandbox_execution_request(
            SandboxExecutionRequest(
                execution_id=EXECUTION_ID,
                workspace_name="worker-example",
                goal="Fix the test.",
            )
        )
    )

    assert response.status is SandboxExecutionStatus.ACCEPTED
    assert response.execution_id == EXECUTION_ID
    assert response.summary == "sandbox completed"

    assert backend.calls == [
        (
            SandboxExecutionRequest(
                execution_id=EXECUTION_ID,
                workspace_name="worker-example",
                goal="Fix the test.",
            ),
            workspace.resolve(),
        )
    ]


@pytest.mark.asyncio
async def test_handler_rejects_authority_bearing_field(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    workspace = root / "worker-example"
    workspace.mkdir()

    backend = RecordingBackend()
    handler = build_handler(
        root=root,
        backend=backend,
    )

    payload = json.loads(
        serialize_sandbox_execution_request(
            SandboxExecutionRequest(
                execution_id=EXECUTION_ID,
                workspace_name="worker-example",
                goal="Fix the test.",
            )
        )
    )
    payload["image"] = "attacker/image:latest"

    response = await handler.handle(json.dumps(payload))

    assert response.status is SandboxExecutionStatus.ERROR
    assert response.execution_id is None
    assert response.error_code == "invalid_sandbox_request"
    assert backend.calls == []


@pytest.mark.asyncio
async def test_handler_rejects_unknown_workspace(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    backend = RecordingBackend()
    handler = build_handler(
        root=root,
        backend=backend,
    )

    response = await handler.handle(
        serialize_sandbox_execution_request(
            SandboxExecutionRequest(
                execution_id=EXECUTION_ID,
                workspace_name="worker-missing",
                goal="Fix the test.",
            )
        )
    )

    assert response.status is SandboxExecutionStatus.ERROR
    assert response.execution_id == EXECUTION_ID
    assert response.error_code == "invalid_workspace"
    assert backend.calls == []


@pytest.mark.asyncio
async def test_handler_hides_backend_failure(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    workspace = root / "worker-example"
    workspace.mkdir()

    class FailingBackend:
        async def execute(
            self,
            request: SandboxExecutionRequest,
            *,
            workspace: Path,
        ) -> SandboxExecutionOutcome:
            del request, workspace
            raise RuntimeError("secret backend detail")

    handler = TrustedSandboxExecutionHandler(
        workspace_resolver=TrustedWorkspaceResolver(workspace_root=root),
        backend=FailingBackend(),
    )

    response = await handler.handle(
        serialize_sandbox_execution_request(
            SandboxExecutionRequest(
                execution_id=EXECUTION_ID,
                workspace_name="worker-example",
                goal="Fix the test.",
            )
        )
    )

    assert response.status is SandboxExecutionStatus.ERROR
    assert response.execution_id == EXECUTION_ID
    assert response.error_code == "execution_failed"

    serialized = json.dumps(
        {
            "error_code": response.error_code,
        }
    )
    assert "secret backend detail" not in serialized


def test_response_protocol_round_trip() -> None:
    from agent_platform.trust.sandbox_execution import (
        SandboxExecutionResponse,
        serialize_sandbox_execution_response,
    )

    original = SandboxExecutionResponse(
        status=SandboxExecutionStatus.ACCEPTED,
        execution_id=EXECUTION_ID,
        summary="done",
    )

    decoded = deserialize_sandbox_execution_response(serialize_sandbox_execution_response(original))

    assert decoded == original
