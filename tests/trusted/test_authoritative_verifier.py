from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.trust.authoritative_verifier import (
    AuthoritativeVerifier,
    VerificationEvidenceMismatchError,
)
from agent_platform.trust.verification import (
    VerificationOutcome,
    VerificationResult,
    VerificationStepResult,
)
from agent_platform.trust.verification_profile import (
    AuthoritativeVerificationProfile,
    VerificationCheck,
)


class RecordingVerificationExecutor:
    def __init__(
        self,
        result: VerificationResult,
    ) -> None:
        self.result = result
        self.workspace: Path | None = None
        self.profile: AuthoritativeVerificationProfile | None = None

    async def execute(
        self,
        *,
        workspace: Path,
        profile: AuthoritativeVerificationProfile,
    ) -> VerificationResult:
        self.workspace = workspace
        self.profile = profile
        return self.result


def _passing_result(
    *,
    profile_version: str = "m12-v0",
    checks: tuple[VerificationCheck, ...] | None = None,
) -> VerificationResult:
    selected_checks = checks or tuple(
        step.check for step in AuthoritativeVerificationProfile().steps
    )

    return VerificationResult(
        profile_version=profile_version,
        outcome=VerificationOutcome.PASS,
        reason_code="all_checks_passed",
        steps=tuple(
            VerificationStepResult(
                check=check,
                outcome=VerificationOutcome.PASS,
                exit_code=0,
            )
            for check in selected_checks
        ),
    )


@pytest.mark.asyncio
async def test_authoritative_verifier_supplies_fixed_platform_profile() -> None:
    executor = RecordingVerificationExecutor(_passing_result())
    verifier = AuthoritativeVerifier(executor=executor)
    workspace = Path("/tmp/verification-workspace")

    result = await verifier.verify(workspace=workspace)

    assert result.outcome is VerificationOutcome.PASS
    assert verifier.profile_version == "m12-v0"
    assert executor.workspace == workspace
    assert executor.profile == AuthoritativeVerificationProfile()


@pytest.mark.asyncio
async def test_authoritative_verifier_rejects_wrong_profile_version() -> None:
    executor = RecordingVerificationExecutor(_passing_result(profile_version="model-controlled"))
    verifier = AuthoritativeVerifier(executor=executor)

    with pytest.raises(VerificationEvidenceMismatchError, match="profile version"):
        await verifier.verify(workspace=Path("/tmp/verification-workspace"))


@pytest.mark.asyncio
async def test_authoritative_verifier_rejects_missing_check() -> None:
    checks = tuple(step.check for step in AuthoritativeVerificationProfile().steps)[:-1]

    executor = RecordingVerificationExecutor(_passing_result(checks=checks))
    verifier = AuthoritativeVerifier(executor=executor)

    with pytest.raises(VerificationEvidenceMismatchError, match="exact order"):
        await verifier.verify(workspace=Path("/tmp/verification-workspace"))


@pytest.mark.asyncio
async def test_authoritative_verifier_rejects_reordered_checks() -> None:
    checks = tuple(step.check for step in AuthoritativeVerificationProfile().steps)
    reordered = (checks[1], checks[0], *checks[2:])

    executor = RecordingVerificationExecutor(_passing_result(checks=reordered))
    verifier = AuthoritativeVerifier(executor=executor)

    with pytest.raises(VerificationEvidenceMismatchError, match="exact order"):
        await verifier.verify(workspace=Path("/tmp/verification-workspace"))


@pytest.mark.asyncio
async def test_authoritative_verifier_preserves_fail_result_when_evidence_is_complete() -> None:
    profile = AuthoritativeVerificationProfile()

    steps = []
    for step in profile.steps:
        outcome = (
            VerificationOutcome.FAIL
            if step.check is VerificationCheck.TEST
            else VerificationOutcome.PASS
        )
        steps.append(
            VerificationStepResult(
                check=step.check,
                outcome=outcome,
                exit_code=1 if outcome is VerificationOutcome.FAIL else 0,
            )
        )

    executor = RecordingVerificationExecutor(
        VerificationResult(
            profile_version=profile.version,
            outcome=VerificationOutcome.FAIL,
            reason_code="check_failed",
            steps=tuple(steps),
        )
    )
    verifier = AuthoritativeVerifier(executor=executor)

    result = await verifier.verify(workspace=Path("/tmp/verification-workspace"))

    assert result.outcome is VerificationOutcome.FAIL
    assert result.reason_code == "check_failed"
