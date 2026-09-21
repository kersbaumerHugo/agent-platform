from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.trust.sandbox_execution import (
    TrustedWorkspaceResolver,
)
from agent_platform.trust.verification import (
    VerificationOutcome,
    VerificationResult,
    VerificationStepResult,
)
from agent_platform.trust.verification_profile import (
    VerificationCheck,
)
from agent_platform.trust.verification_service import (
    TrustedVerificationClient,
    TrustedVerificationClientError,
    TrustedVerificationHandler,
    UnixSocketVerificationServer,
)


def _passing_result() -> VerificationResult:
    return VerificationResult(
        profile_version="m12-v0",
        outcome=VerificationOutcome.PASS,
        reason_code="all_checks_passed",
        steps=(
            VerificationStepResult(
                check=VerificationCheck.SYNTAX,
                outcome=VerificationOutcome.PASS,
                exit_code=0,
                summary="pass",
            ),
        ),
    )


class PassingVerifier:
    async def verify(
        self,
        *,
        workspace: Path,
    ) -> VerificationResult:
        assert workspace.is_dir()
        return _passing_result()


@pytest.mark.asyncio
async def test_client_crosses_trusted_verifier_socket(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    workspace = root / "verification-example"
    workspace.mkdir()

    socket_path = tmp_path / "verifier.sock"

    server = UnixSocketVerificationServer(
        socket_path=socket_path,
        handler=TrustedVerificationHandler(
            workspace_resolver=TrustedWorkspaceResolver(
                workspace_root=root,
            ),
            verifier=PassingVerifier(),
        ),
    )

    await server.start()

    try:
        client = TrustedVerificationClient(
            socket_path=socket_path,
            workspace_root=root,
        )

        result = await client.verify(
            workspace=workspace,
        )
    finally:
        await server.close()

    assert result == _passing_result()
    assert not socket_path.exists()


@pytest.mark.asyncio
async def test_client_rejects_workspace_outside_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()

    client = TrustedVerificationClient(
        socket_path=tmp_path / "missing.sock",
        workspace_root=root,
    )

    with pytest.raises(
        TrustedVerificationClientError,
        match="outside trusted root",
    ):
        await client.verify(
            workspace=outside,
        )


@pytest.mark.asyncio
async def test_handler_hides_verifier_failure(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    workspace = root / "verification-example"
    workspace.mkdir()

    class FailingVerifier:
        async def verify(
            self,
            *,
            workspace: Path,
        ) -> VerificationResult:
            del workspace
            raise RuntimeError("secret verifier detail")

    handler = TrustedVerificationHandler(
        workspace_resolver=TrustedWorkspaceResolver(
            workspace_root=root,
        ),
        verifier=FailingVerifier(),
    )

    from agent_platform.trust.verification_service import (
        VerificationServiceRequest,
        serialize_verification_request,
    )

    response = await handler.handle(
        serialize_verification_request(
            VerificationServiceRequest(
                workspace_name=workspace.name,
            )
        )
    )

    assert response.error_code == "verification_failed"
