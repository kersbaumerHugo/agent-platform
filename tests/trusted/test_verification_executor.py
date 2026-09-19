from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agent_platform.trust.verification import VerificationOutcome
from agent_platform.trust.verification_executor import (
    ProfileVerificationExecutor,
    SubprocessVerificationProcessRunner,
    VerificationProcessOutcome,
    VerificationProcessResult,
)
from agent_platform.trust.verification_profile import (
    AuthoritativeVerificationProfile,
    VerificationCheck,
)


class SequenceRunner:
    def __init__(
        self,
        results: tuple[VerificationProcessResult, ...],
    ) -> None:
        self._results = list(results)
        self.calls: list[tuple[Path, tuple[str, ...]]] = []

    async def run(
        self,
        *,
        workspace: Path,
        argv: tuple[str, ...],
    ) -> VerificationProcessResult:
        self.calls.append((workspace, argv))
        return self._results.pop(0)


def _exited(exit_code: int) -> VerificationProcessResult:
    return VerificationProcessResult(
        outcome=VerificationProcessOutcome.EXITED,
        exit_code=exit_code,
    )


@pytest.mark.asyncio
async def test_profile_executor_runs_every_authoritative_step_in_order(tmp_path: Path) -> None:
    profile = AuthoritativeVerificationProfile()
    runner = SequenceRunner(tuple(_exited(0) for _ in profile.steps))
    executor = ProfileVerificationExecutor(runner=runner)

    result = await executor.execute(
        workspace=tmp_path,
        profile=profile,
    )

    assert result.outcome is VerificationOutcome.PASS
    assert result.reason_code == "all_checks_passed"
    assert tuple(argv for _, argv in runner.calls) == tuple(step.argv for step in profile.steps)
    assert tuple(step.check for step in result.steps) == tuple(step.check for step in profile.steps)


@pytest.mark.asyncio
async def test_profile_executor_preserves_complete_evidence_after_failure(
    tmp_path: Path,
) -> None:
    profile = AuthoritativeVerificationProfile()
    results = [_exited(0) for _ in profile.steps]
    results[4] = _exited(1)
    runner = SequenceRunner(tuple(results))
    executor = ProfileVerificationExecutor(runner=runner)

    result = await executor.execute(
        workspace=tmp_path,
        profile=profile,
    )

    assert result.outcome is VerificationOutcome.FAIL
    assert result.reason_code == "check_failed"
    assert len(runner.calls) == len(profile.steps)
    assert result.steps[4].check is VerificationCheck.TEST
    assert result.steps[4].outcome is VerificationOutcome.FAIL
    assert result.steps[4].summary == "verification_step_failed"


@pytest.mark.asyncio
async def test_profile_executor_maps_timeout_to_error_and_continues(
    tmp_path: Path,
) -> None:
    profile = AuthoritativeVerificationProfile()
    results = [_exited(0) for _ in profile.steps]
    results[0] = VerificationProcessResult(
        outcome=VerificationProcessOutcome.TIMEOUT,
        exit_code=None,
    )
    runner = SequenceRunner(tuple(results))
    executor = ProfileVerificationExecutor(runner=runner)

    result = await executor.execute(
        workspace=tmp_path,
        profile=profile,
    )

    assert result.outcome is VerificationOutcome.ERROR
    assert result.reason_code == "verification_error"
    assert len(result.steps) == len(profile.steps)
    assert result.steps[0].summary == "verification_step_timeout"


@pytest.mark.asyncio
async def test_subprocess_runner_executes_argv_without_shell(tmp_path: Path) -> None:
    marker = tmp_path / "should-not-exist"
    runner = SubprocessVerificationProcessRunner(timeout_seconds=5.0)

    result = await runner.run(
        workspace=tmp_path,
        argv=(
            sys.executable,
            "-c",
            "import sys; sys.exit(0)",
            f";touch {marker}",
        ),
    )

    assert result.outcome is VerificationProcessOutcome.EXITED
    assert result.exit_code == 0
    assert not marker.exists()


@pytest.mark.asyncio
async def test_subprocess_runner_enforces_hard_timeout(tmp_path: Path) -> None:
    runner = SubprocessVerificationProcessRunner(
        timeout_seconds=0.05,
        terminate_grace_seconds=0.05,
    )

    result = await runner.run(
        workspace=tmp_path,
        argv=(
            sys.executable,
            "-c",
            "import time; time.sleep(5)",
        ),
    )

    assert result.outcome is VerificationProcessOutcome.TIMEOUT
    assert result.exit_code is None


@pytest.mark.asyncio
async def test_subprocess_runner_does_not_forward_publication_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "must-not-cross-verification-boundary")
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-cross-verification-boundary")
    monkeypatch.setenv("MODEL_GATEWAY_API_KEY", "must-not-cross-verification-boundary")

    runner = SubprocessVerificationProcessRunner(timeout_seconds=5.0)

    result = await runner.run(
        workspace=tmp_path,
        argv=(
            sys.executable,
            "-c",
            (
                "import os,sys;"
                "blocked=('GH_TOKEN','GITHUB_TOKEN','MODEL_GATEWAY_API_KEY');"
                "sys.exit(1 if any(name in os.environ for name in blocked) else 0)"
            ),
        ),
    )

    assert result.outcome is VerificationProcessOutcome.EXITED
    assert result.exit_code == 0


def test_subprocess_runner_uses_minimal_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNRELATED_SECRET", "secret")
    environment = SubprocessVerificationProcessRunner._environment()

    assert "PATH" in environment
    assert environment["HOME"] == "/tmp"
    assert environment["TMPDIR"] == "/tmp"
    assert "UNRELATED_SECRET" not in environment
    assert "GH_TOKEN" not in environment
    assert "GITHUB_TOKEN" not in environment
