from collections.abc import Sequence
from typing import Protocol

from agent_platform.domain.memory import (
    MemoryRecord,
    RetrievalAcceptanceDecision,
    RetrievalHit,
    RetrievalQuery,
)


class MemoryStoreContract(Protocol):
    async def store(self, record: MemoryRecord) -> None: ...


class RetrievalContract(Protocol):
    async def retrieve(
        self,
        query: RetrievalQuery,
    ) -> list[RetrievalHit]: ...


class RetrievalAcceptanceContract(Protocol):
    async def evaluate(
        self,
        query: RetrievalQuery,
        hits: Sequence[RetrievalHit],
    ) -> RetrievalAcceptanceDecision: ...
