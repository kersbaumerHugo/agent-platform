from __future__ import annotations

from pathlib import Path

from agent_platform.trust.verification import (
    VerificationExecutor,
    VerificationResult,
)
from agent_platform.trust.verification_profile import (
    AuthoritativeVerificationProfile,
)


class VerificationEvidenceMismatchError(RuntimeError):
    """Raised when executor evidence does not prove the authoritative profile exactly."""


class AuthoritativeVerifier:
    """Run the fixed M12 V0 profile and validate executor evidence fail-closed."""

    def __init__(
        self,
        *,
        executor: VerificationExecutor,
    ) -> None:
        self._executor = executor
        self._profile = AuthoritativeVerificationProfile()

    @property
    def profile_version(self) -> str:
        return self._profile.version

    async def verify(
        self,
        *,
        workspace: Path,
    ) -> VerificationResult:
        result = await self._executor.execute(
            workspace=workspace,
            profile=self._profile,
        )

        self._validate_evidence(result)

        return result

    def _validate_evidence(
        self,
        result: VerificationResult,
    ) -> None:
        if result.profile_version != self._profile.version:
            raise VerificationEvidenceMismatchError(
                "Verification result profile version does not match the authoritative profile."
            )

        expected_checks = tuple(step.check for step in self._profile.steps)
        actual_checks = tuple(step.check for step in result.steps)

        if actual_checks != expected_checks:
            raise VerificationEvidenceMismatchError(
                "Verification result does not contain the authoritative checks in exact order."
            )
