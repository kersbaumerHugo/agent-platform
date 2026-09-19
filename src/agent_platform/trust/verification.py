from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from agent_platform.trust.verification_profile import (
    AuthoritativeVerificationProfile,
    VerificationCheck,
)

MAX_VERIFICATION_SUMMARY_CHARS = 4096


class VerificationOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


@dataclass(frozen=True)
class VerificationStepResult:
    check: VerificationCheck
    outcome: VerificationOutcome
    exit_code: int | None
    summary: str = ""

    def __post_init__(self) -> None:
        if len(self.summary) > MAX_VERIFICATION_SUMMARY_CHARS:
            raise ValueError("Verification step summary exceeds the protocol limit.")

        if self.outcome is VerificationOutcome.PASS and self.exit_code != 0:
            raise ValueError("Passing verification steps require exit_code 0.")

        if self.outcome is VerificationOutcome.FAIL and (
            self.exit_code is None or self.exit_code == 0
        ):
            raise ValueError("Failing verification steps require a non-zero exit_code.")


@dataclass(frozen=True)
class VerificationResult:
    profile_version: str
    outcome: VerificationOutcome
    reason_code: str
    steps: tuple[VerificationStepResult, ...]

    def __post_init__(self) -> None:
        if not self.profile_version.strip():
            raise ValueError("profile_version must not be empty.")

        if not self.reason_code.strip():
            raise ValueError("reason_code must not be empty.")

        if not self.steps:
            raise ValueError("VerificationResult must contain at least one step result.")

        checks = tuple(step.check for step in self.steps)

        if len(checks) != len(set(checks)):
            raise ValueError("VerificationResult must not contain duplicate checks.")

        has_fail = any(step.outcome is VerificationOutcome.FAIL for step in self.steps)
        has_error = any(step.outcome is VerificationOutcome.ERROR for step in self.steps)
        all_pass = all(step.outcome is VerificationOutcome.PASS for step in self.steps)

        if self.outcome is VerificationOutcome.PASS and not all_pass:
            raise ValueError("Passing verification results require all executed steps to pass.")

        if self.outcome is VerificationOutcome.FAIL and (not has_fail or has_error):
            raise ValueError(
                "Failing verification results require at least one failed step and no errors."
            )

        if self.outcome is VerificationOutcome.ERROR and not has_error:
            raise ValueError("Error verification results require at least one errored step.")


class VerificationExecutor(Protocol):
    """Execute one platform-owned verification profile in an isolated workspace."""

    async def execute(
        self,
        *,
        workspace: Path,
        profile: AuthoritativeVerificationProfile,
    ) -> VerificationResult: ...
