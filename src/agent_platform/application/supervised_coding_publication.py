from __future__ import annotations

import re
from typing import Protocol

from agent_platform.application.supervised_coding import PreparedCodingTask
from agent_platform.domain.coding import (
    CodingPublicationOutcome,
    CodingResult,
    CodingTask,
    CodingVerificationOutcome,
)
from agent_platform.trust.publisher import ChangeSet
from agent_platform.trust.verification_binding import VerifiedChangeSet
from agent_platform.trust.verified_publication import VerifiedPublicationResult

_GITHUB_PULL_REQUEST_PATTERN = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/([1-9][0-9]*)$"
)


class CodingPreparationService(Protocol):
    async def execute(
        self,
        task: CodingTask,
    ) -> PreparedCodingTask: ...


class CodingVerificationService(Protocol):
    async def verify(
        self,
        change_set: ChangeSet,
    ) -> VerifiedChangeSet: ...


class CodingVerifiedPublisher(Protocol):
    async def publish(
        self,
        verified: VerifiedChangeSet,
    ) -> VerifiedPublicationResult: ...


class CodingPublicationIdentityMismatchError(RuntimeError):
    pass


class CodingTaskIdentityMismatchError(RuntimeError):
    pass


class SupervisedCodingPublicationService:
    """Prepare, verify, and publish one supervised coding task fail-closed."""

    def __init__(
        self,
        *,
        preparation: CodingPreparationService,
        verification: CodingVerificationService,
        publisher: CodingVerifiedPublisher,
    ) -> None:
        self._preparation = preparation
        self._verification = verification
        self._publisher = publisher

    async def execute(
        self,
        task: CodingTask,
    ) -> CodingResult:
        prepared = await self._preparation.execute(task)

        if prepared.task_id != task.task_id:
            raise CodingTaskIdentityMismatchError(
                "Prepared coding task identity does not match requested task."
            )

        verified = await self._verification.verify(
            prepared.change_set,
        )

        publication = await self._publisher.publish(verified)

        if publication.identity != verified.identity:
            raise CodingPublicationIdentityMismatchError(
                "Published ChangeSet identity does not match verified ChangeSet."
            )

        pull_request_match = _GITHUB_PULL_REQUEST_PATTERN.fullmatch(publication.reference)
        pull_request_number = (
            int(pull_request_match.group(1)) if pull_request_match is not None else None
        )

        return CodingResult(
            task_id=prepared.task_id,
            execution_id=prepared.execution_id,
            base_revision=verified.change_set.base_revision,
            change_set_identity=verified.identity.reference,
            changed_paths=verified.change_set.changed_paths,
            verification_profile_version=verified.verification.profile_version,
            verification_outcome=CodingVerificationOutcome(verified.verification.outcome.value),
            publication_outcome=CodingPublicationOutcome.PUBLISHED,
            publication_reference=publication.reference,
            pull_request_number=pull_request_number,
        )
