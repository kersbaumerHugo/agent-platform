from __future__ import annotations

from typing import Protocol

from agent_platform.application.supervised_coding import PreparedCodingTask
from agent_platform.domain.coding import CodingTask
from agent_platform.trust.publisher import ChangeSet
from agent_platform.trust.verification_binding import VerifiedChangeSet
from agent_platform.trust.verified_publication import VerifiedPublicationResult


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
    ) -> VerifiedPublicationResult:
        prepared = await self._preparation.execute(task)

        verified = await self._verification.verify(
            prepared.change_set,
        )

        publication = await self._publisher.publish(verified)

        if publication.identity != verified.identity:
            raise CodingPublicationIdentityMismatchError(
                "Published ChangeSet identity does not match verified ChangeSet."
            )

        return publication
