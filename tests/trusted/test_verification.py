from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.trust.verification import (
    MAX_VERIFICATION_SUMMARY_CHARS,
    VerificationOutcome,
    VerificationResult,
    VerificationStepResult,
)
from agent_platform.trust.verification_profile import VerificationCheck


def test_step_result_accepts_pass_fail_and_error_shapes() -> None:
    passed = VerificationStepResult(
        check=VerificationCheck.SYNTAX,
        outcome=VerificationOutcome.PASS,
        exit_code=0,
        summary="ok",
    )
    failed = VerificationStepResult(
        check=VerificationCheck.RUFF_LINT,
        outcome=VerificationOutcome.FAIL,
        exit_code=1,
        summary="lint failed",
    )
    errored = VerificationStepResult(
        check=VerificationCheck.TEST,
        outcome=VerificationOutcome.ERROR,
        exit_code=None,
        summary="timeout",
    )

    assert passed.exit_code == 0
    assert failed.exit_code == 1
    assert errored.exit_code is None


def test_step_result_rejects_inconsistent_exit_codes() -> None:
    with pytest.raises(ValueError, match="exit_code 0"):
        VerificationStepResult(
            check=VerificationCheck.SYNTAX,
            outcome=VerificationOutcome.PASS,
            exit_code=1,
        )

    with pytest.raises(ValueError, match="non-zero"):
        VerificationStepResult(
            check=VerificationCheck.RUFF_LINT,
            outcome=VerificationOutcome.FAIL,
            exit_code=0,
        )


def test_step_result_bounds_evidence_summary() -> None:
    with pytest.raises(ValueError, match="protocol limit"):
        VerificationStepResult(
            check=VerificationCheck.TEST,
            outcome=VerificationOutcome.ERROR,
            exit_code=None,
            summary="x" * (MAX_VERIFICATION_SUMMARY_CHARS + 1),
        )


def test_verification_result_accepts_consistent_outcomes() -> None:
    passed = VerificationResult(
        profile_version="m12-v0",
        outcome=VerificationOutcome.PASS,
        reason_code="all_checks_passed",
        steps=(
            VerificationStepResult(
                check=VerificationCheck.SYNTAX,
                outcome=VerificationOutcome.PASS,
                exit_code=0,
            ),
        ),
    )
    failed = VerificationResult(
        profile_version="m12-v0",
        outcome=VerificationOutcome.FAIL,
        reason_code="check_failed",
        steps=(
            VerificationStepResult(
                check=VerificationCheck.RUFF_LINT,
                outcome=VerificationOutcome.FAIL,
                exit_code=1,
            ),
        ),
    )
    errored = VerificationResult(
        profile_version="m12-v0",
        outcome=VerificationOutcome.ERROR,
        reason_code="executor_error",
        steps=(
            VerificationStepResult(
                check=VerificationCheck.TEST,
                outcome=VerificationOutcome.ERROR,
                exit_code=None,
            ),
        ),
    )

    assert passed.outcome is VerificationOutcome.PASS
    assert failed.outcome is VerificationOutcome.FAIL
    assert errored.outcome is VerificationOutcome.ERROR


def test_verification_result_rejects_inconsistent_outcome() -> None:
    with pytest.raises(ValueError, match="all executed steps"):
        VerificationResult(
            profile_version="m12-v0",
            outcome=VerificationOutcome.PASS,
            reason_code="invalid",
            steps=(
                VerificationStepResult(
                    check=VerificationCheck.TEST,
                    outcome=VerificationOutcome.FAIL,
                    exit_code=1,
                ),
            ),
        )


def test_verification_result_rejects_duplicate_checks() -> None:
    step = VerificationStepResult(
        check=VerificationCheck.SYNTAX,
        outcome=VerificationOutcome.PASS,
        exit_code=0,
    )

    with pytest.raises(ValueError, match="duplicate"):
        VerificationResult(
            profile_version="m12-v0",
            outcome=VerificationOutcome.PASS,
            reason_code="invalid",
            steps=(step, step),
        )


def test_verification_executor_contract_is_workspace_based() -> None:
    workspace = Path("/tmp/example-verification-workspace")

    assert workspace.name == "example-verification-workspace"
