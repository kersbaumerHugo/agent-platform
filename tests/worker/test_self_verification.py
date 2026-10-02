from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import agent_platform.worker.self_verification as self_verification
from agent_platform.trust.diagnostic_verification import (
    DiagnosticVerificationResult,
)
from agent_platform.worker.self_verification import (
    WorkerSelfVerificationResult,
    build_self_repair_goal,
    run_worker_self_verification,
)


def install_fake_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: DiagnosticVerificationResult,
) -> tuple[
    AsyncMock,
    list[Path],
]:
    verify = AsyncMock(
        return_value=result,
    )
    socket_paths: list[Path] = []

    class FakeClient:
        def __init__(
            self,
            *,
            socket_path: Path,
        ) -> None:
            socket_paths.append(socket_path)

        async def verify(
            self,
        ) -> DiagnosticVerificationResult:
            return await verify()

    monkeypatch.setattr(
        self_verification,
        "TrustedDiagnosticVerificationClient",
        FakeClient,
    )

    return verify, socket_paths


@pytest.mark.asyncio
async def test_self_verification_passes_for_green_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AGENT_PLATFORM_DIAGNOSTIC_VERIFIER_SOCKET",
        "/run/diagnostic-verifier.sock",
    )

    verify, socket_paths = install_fake_client(
        monkeypatch,
        result=DiagnosticVerificationResult(
            exit_code=0,
            output="682 passed in 6.21s",
        ),
    )

    result = await run_worker_self_verification(tmp_path)

    assert result.passed
    assert result.command == (
        "python",
        "-m",
        "pytest",
        "-q",
    )
    assert result.exit_code == 0
    assert not result.timed_out
    assert result.output == ("682 passed in 6.21s")

    verify.assert_awaited_once()
    assert socket_paths == [Path("/run/diagnostic-verifier.sock")]


@pytest.mark.asyncio
async def test_self_verification_preserves_failure_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AGENT_PLATFORM_DIAGNOSTIC_VERIFIER_SOCKET",
        "/run/diagnostic-verifier.sock",
    )

    install_fake_client(
        monkeypatch,
        result=DiagnosticVerificationResult(
            exit_code=1,
            output=("NameError: ToolDefinition is not defined"),
        ),
    )

    result = await run_worker_self_verification(tmp_path)

    assert not result.passed
    assert result.exit_code == 1
    assert not result.timed_out
    assert "NameError: ToolDefinition" in result.output


@pytest.mark.asyncio
async def test_self_verification_preserves_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AGENT_PLATFORM_DIAGNOSTIC_VERIFIER_SOCKET",
        "/run/diagnostic-verifier.sock",
    )

    install_fake_client(
        monkeypatch,
        result=DiagnosticVerificationResult(
            exit_code=None,
            output="partial output",
            timed_out=True,
        ),
    )

    result = await run_worker_self_verification(tmp_path)

    assert not result.passed
    assert result.exit_code is None
    assert result.timed_out
    assert result.output == "partial output"


@pytest.mark.asyncio
async def test_self_verification_fails_closed_without_socket(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv(
        "AGENT_PLATFORM_DIAGNOSTIC_VERIFIER_SOCKET",
        raising=False,
    )

    with pytest.raises(
        RuntimeError,
        match="not configured",
    ):
        await run_worker_self_verification(tmp_path)


@pytest.mark.asyncio
async def test_self_verification_rejects_relative_socket(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AGENT_PLATFORM_DIAGNOSTIC_VERIFIER_SOCKET",
        "diagnostic.sock",
    )

    with pytest.raises(
        RuntimeError,
        match="absolute path",
    ):
        await run_worker_self_verification(tmp_path)


def test_repair_goal_contains_real_verification_evidence() -> None:
    verification = WorkerSelfVerificationResult(
        command=(
            "python",
            "-m",
            "pytest",
            "-q",
        ),
        exit_code=1,
        output="3 failed in 0.36s",
    )

    goal = build_self_repair_goal(
        original_goal=("Implement the focused regression."),
        verification=verification,
    )

    assert "single bounded self-repair attempt" in goal
    assert "python -m pytest -q" in goal
    assert "exit_code: 1" in goal
    assert "3 failed in 0.36s" in goal
    assert "Do not weaken or delete tests" in goal


def test_phase_limited_repair_goal_explains_incomplete_attempt() -> None:
    verification = WorkerSelfVerificationResult(
        command=(
            "python",
            "-m",
            "pytest",
            "-q",
        ),
        exit_code=0,
        output="693 passed",
    )

    goal = build_self_repair_goal(
        original_goal=("Implement the focused change."),
        verification=verification,
        phase_limited=True,
    )

    assert "phase limit before completing" in goal
    assert "single bounded self-repair attempt" in goal
    assert "693 passed" in goal
