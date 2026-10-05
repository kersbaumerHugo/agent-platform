from __future__ import annotations

import json
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agent_platform.trust.change_set_identity import (
    ChangeSetIdentity,
    identify_change_set,
)
from agent_platform.trust.change_set_materializer import MaterializedChangeSet
from agent_platform.trust.publisher import ChangeSet
from agent_platform.trust.verification import (
    MAX_VERIFICATION_SUMMARY_CHARS,
    VerificationOutcome,
    VerificationResult,
)


class ChangeSetMaterializer(Protocol):
    def materialize(
        self,
        change_set: ChangeSet,
    ) -> AbstractContextManager[MaterializedChangeSet]: ...

    def assert_exact(
        self,
        *,
        materialized: MaterializedChangeSet,
        change_set: ChangeSet,
    ) -> None: ...


class AuthoritativeChangeVerifier(Protocol):
    async def verify(
        self,
        *,
        workspace: Path,
    ) -> VerificationResult: ...


class VerificationRejectedError(RuntimeError):
    def __init__(
        self,
        result: VerificationResult,
    ) -> None:
        self.result = result

        diagnostics = self._render_diagnostics(result)
        message = f"Authoritative verification rejected ChangeSet: {result.reason_code}."

        if diagnostics:
            message += f" Untrusted verification diagnostics: {diagnostics}"

        super().__init__(message)

    @staticmethod
    def _render_diagnostics(
        result: VerificationResult,
    ) -> str:
        rendered_steps: list[str] = []

        for step in result.steps:
            if step.outcome is VerificationOutcome.PASS:
                continue

            exit_code = str(step.exit_code) if step.exit_code is not None else "none"

            rendered_steps.append(
                f"check={step.check.value}; "
                f"outcome={step.outcome.value}; "
                f"exit_code={exit_code}; "
                "untrusted_summary_json="
                f"{json.dumps(step.summary, ensure_ascii=False)}"
            )

        diagnostics = " | ".join(rendered_steps)

        return diagnostics[:MAX_VERIFICATION_SUMMARY_CHARS]


class ChangeSetIdentityMismatchError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedChangeSet:
    """Capability token proving one exact ChangeSet passed authoritative verification."""

    change_set: ChangeSet
    identity: ChangeSetIdentity
    verification: VerificationResult

    def __post_init__(self) -> None:
        if self.verification.outcome is not VerificationOutcome.PASS:
            raise ValueError("VerifiedChangeSet requires a passing verification result.")

        if identify_change_set(self.change_set) != self.identity:
            raise ValueError("VerifiedChangeSet identity does not match ChangeSet.")


class ChangeSetVerificationService:
    """Bind authoritative verification evidence to one exact ChangeSet."""

    def __init__(
        self,
        *,
        materializer: ChangeSetMaterializer,
        verifier: AuthoritativeChangeVerifier,
    ) -> None:
        self._materializer = materializer
        self._verifier = verifier

    async def verify(
        self,
        change_set: ChangeSet,
    ) -> VerifiedChangeSet:
        expected_identity = identify_change_set(change_set)

        with self._materializer.materialize(change_set) as materialized:
            if materialized.identity != expected_identity:
                raise ChangeSetIdentityMismatchError(
                    "Materialized ChangeSet identity does not match requested ChangeSet."
                )

            result = await self._verifier.verify(
                workspace=materialized.workspace,
            )

            self._materializer.assert_exact(
                materialized=materialized,
                change_set=change_set,
            )

        if result.outcome is not VerificationOutcome.PASS:
            raise VerificationRejectedError(result)

        return VerifiedChangeSet(
            change_set=change_set,
            identity=expected_identity,
            verification=result,
        )
