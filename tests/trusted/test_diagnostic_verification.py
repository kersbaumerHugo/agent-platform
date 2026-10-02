from pathlib import Path

import pytest

from agent_platform.trust.diagnostic_verification import (
    DiagnosticVerificationResult,
    TrustedDiagnosticVerificationClient,
    TrustedDiagnosticVerificationClientError,
    TrustedDiagnosticVerificationHandler,
    UnixSocketDiagnosticVerificationServer,
)


class FakeDiagnosticAuthority:
    def __init__(
        self,
        result: DiagnosticVerificationResult,
    ) -> None:
        self.result = result
        self.calls = 0

    async def verify(
        self,
    ) -> DiagnosticVerificationResult:
        self.calls += 1
        return self.result


@pytest.mark.asyncio
async def test_client_receives_diagnostic_result(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "diagnostic.sock"

    authority = FakeDiagnosticAuthority(
        DiagnosticVerificationResult(
            exit_code=1,
            output="1 failed, 682 passed",
        )
    )

    handler = TrustedDiagnosticVerificationHandler(
        authority=authority,
    )

    server = UnixSocketDiagnosticVerificationServer(
        socket_path=socket_path,
        handler=handler,
    )

    await server.start()

    try:
        client = TrustedDiagnosticVerificationClient(
            socket_path=socket_path,
        )

        result = await client.verify()

        assert result.exit_code == 1
        assert result.timed_out is False
        assert result.output == "1 failed, 682 passed"
        assert authority.calls == 1
        assert handler.requests_consumed == 1
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_diagnostic_request_budget_is_bounded(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "diagnostic.sock"

    authority = FakeDiagnosticAuthority(
        DiagnosticVerificationResult(
            exit_code=0,
            output="682 passed",
        )
    )

    handler = TrustedDiagnosticVerificationHandler(
        authority=authority,
        max_requests=2,
    )

    server = UnixSocketDiagnosticVerificationServer(
        socket_path=socket_path,
        handler=handler,
    )

    await server.start()

    try:
        client = TrustedDiagnosticVerificationClient(
            socket_path=socket_path,
        )

        await client.verify()
        await client.verify()

        with pytest.raises(
            TrustedDiagnosticVerificationClientError,
            match="diagnostic_request_budget_exhausted",
        ):
            await client.verify()

        assert authority.calls == 2
        assert handler.requests_consumed == 2
    finally:
        await server.close()


def test_timed_out_result_has_no_exit_code() -> None:
    result = DiagnosticVerificationResult(
        exit_code=None,
        output="partial output",
        timed_out=True,
    )

    assert result.exit_code is None
    assert result.timed_out is True


def test_completed_result_requires_exit_code() -> None:
    with pytest.raises(
        ValueError,
        match="requires an exit code",
    ):
        DiagnosticVerificationResult(
            exit_code=None,
            output="",
        )


def test_output_is_bounded() -> None:
    with pytest.raises(
        ValueError,
        match="output exceeds limit",
    ):
        DiagnosticVerificationResult(
            exit_code=1,
            output="x" * 8193,
        )
