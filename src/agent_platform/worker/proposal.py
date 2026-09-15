from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_platform.trust.publisher import ChangeSet
from agent_platform.worker.publication import (
    TrustedPublicationResponse,
)
from agent_platform.worker.session import (
    WorkerDevelopmentSession,
    WorkerDevelopmentTask,
)


class ChangeProposalPublisher(Protocol):
    async def publish(
        self,
        change_set: ChangeSet,
    ) -> TrustedPublicationResponse: ...


@dataclass(frozen=True)
class WorkerProposalResult:
    change_set: ChangeSet
    publication: TrustedPublicationResponse


class WorkerProposalRunner:
    """Run one Worker development task and submit its proposal for trust evaluation."""

    def __init__(
        self,
        *,
        session: WorkerDevelopmentSession,
        publisher: ChangeProposalPublisher,
    ) -> None:
        self._session = session
        self._publisher = publisher

    async def run(
        self,
        task: WorkerDevelopmentTask,
    ) -> WorkerProposalResult:
        change_set = await self._session.run(task)

        publication = await self._publisher.publish(change_set)

        return WorkerProposalResult(
            change_set=change_set,
            publication=publication,
        )
