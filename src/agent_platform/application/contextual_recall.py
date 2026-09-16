from collections.abc import Sequence
from dataclasses import dataclass

from agent_platform.contracts.memory import (
    RetrievalAcceptanceContract,
    RetrievalContract,
)
from agent_platform.domain.context import ContextRef
from agent_platform.domain.memory import (
    MemoryScope,
    RetrievalAcceptanceDecision,
    RetrievalDecision,
    RetrievalHit,
    RetrievalQuery,
)


@dataclass(frozen=True)
class ContextualRecallResult:
    context: ContextRef
    decision: RetrievalAcceptanceDecision
    hits: tuple[RetrievalHit, ...]


class ContextualRecall:
    def __init__(
        self,
        *,
        retrieval: RetrievalContract,
        acceptance: RetrievalAcceptanceContract,
    ) -> None:
        self._retrieval = retrieval
        self._acceptance = acceptance

    async def recall(
        self,
        *,
        contexts: Sequence[ContextRef],
        text: str,
        limit_per_context: int = 5,
    ) -> list[ContextualRecallResult]:
        if limit_per_context <= 0:
            raise ValueError("limit_per_context must be greater than 0.")

        results: list[ContextualRecallResult] = []

        for context in contexts:
            query = RetrievalQuery(
                scope=MemoryScope(
                    namespace=context.namespace,
                ),
                text=text,
                limit=limit_per_context,
            )

            hits = await self._retrieval.retrieve(query)
            decision = await self._acceptance.evaluate(
                query,
                hits,
            )

            accepted_hits = tuple(hits) if decision.decision is RetrievalDecision.ACCEPT else ()

            results.append(
                ContextualRecallResult(
                    context=context,
                    decision=decision,
                    hits=accepted_hits,
                )
            )

        return results
