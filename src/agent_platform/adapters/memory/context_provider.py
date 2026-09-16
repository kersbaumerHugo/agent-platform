from collections.abc import Sequence

from agent_platform.contracts.memory import (
    RetrievalAcceptanceContract,
    RetrievalContract,
)
from agent_platform.domain.context import (
    ContextContribution,
    ContextItem,
    ContextProvenance,
    ContextRef,
    content_sha256,
)
from agent_platform.domain.context_preparation import RecallRequest
from agent_platform.domain.context_trace import (
    ContextProviderDecision,
    ContextProviderResult,
    ContextProviderTrace,
    ContextSourceEvidence,
)
from agent_platform.domain.memory import (
    MemoryRecord,
    MemoryScope,
    RetrievalDecision,
    RetrievalHit,
    RetrievalQuery,
)


class MemoryContextProvider:
    def __init__(
        self,
        *,
        retrieval: RetrievalContract,
        acceptance: RetrievalAcceptanceContract,
    ) -> None:
        self._retrieval = retrieval
        self._acceptance = acceptance

    @property
    def name(self) -> str:
        return "memory"

    async def provide(
        self,
        request: RecallRequest,
    ) -> ContextProviderResult:
        query = RetrievalQuery(
            scope=MemoryScope(
                namespace=request.context.namespace,
            ),
            text=request.query,
            limit=request.limit,
        )

        hits = await self._retrieval.retrieve(query)
        decision = await self._acceptance.evaluate(
            query,
            hits,
        )

        if decision.decision is not RetrievalDecision.ACCEPT:
            return self._result(
                request=request,
                hits=hits,
                contribution=self._empty_contribution(request.context),
                decision=ContextProviderDecision.ABSTAIN,
                reason_code=decision.reason_code,
            )

        if any(hit.memory.scope.namespace != request.context.namespace for hit in hits):
            return self._result(
                request=request,
                hits=hits,
                contribution=self._empty_contribution(request.context),
                decision=ContextProviderDecision.ABSTAIN,
                reason_code="provider_scope_mismatch",
            )

        ordered_hits = sorted(
            hits,
            key=lambda hit: (
                hit.rank,
                str(hit.memory.id),
            ),
        )
        contribution = ContextContribution(
            provider=self.name,
            context=request.context,
            items=tuple(
                self._to_context_item(
                    context=request.context,
                    hit=hit,
                )
                for hit in ordered_hits
            ),
        )

        return self._result(
            request=request,
            hits=hits,
            contribution=contribution,
            decision=ContextProviderDecision.ACCEPT,
            reason_code=decision.reason_code,
        )

    def _result(
        self,
        *,
        request: RecallRequest,
        hits: Sequence[RetrievalHit],
        contribution: ContextContribution,
        decision: ContextProviderDecision,
        reason_code: str,
    ) -> ContextProviderResult:
        accepted_sources = tuple(
            ContextSourceEvidence(
                source_id=item.provenance.source_id,
                content_hash=item.provenance.content_hash,
            )
            for item in contribution.items
        )
        accepted_count = len(accepted_sources)

        return ContextProviderResult(
            contribution=contribution,
            trace=ContextProviderTrace(
                request_id=request.request_id,
                provider=self.name,
                context=request.context,
                decision=decision,
                reason_code=reason_code,
                candidate_count=len(hits),
                accepted_count=accepted_count,
                rejected_count=len(hits) - accepted_count,
                accepted_sources=accepted_sources,
            ),
        )

    def _empty_contribution(
        self,
        context: ContextRef,
    ) -> ContextContribution:
        return ContextContribution(
            provider=self.name,
            context=context,
        )

    def _to_context_item(
        self,
        *,
        context: ContextRef,
        hit: RetrievalHit,
    ) -> ContextItem:
        memory = hit.memory

        return ContextItem(
            item_id=f"memory:{memory.id}",
            content=memory.content,
            kind=self._memory_kind(memory),
            context=context,
            provenance=ContextProvenance(
                provider=self.name,
                source_id=str(memory.id),
                content_hash=content_sha256(
                    memory.content,
                ),
            ),
        )

    @staticmethod
    def _memory_kind(
        memory: MemoryRecord,
    ) -> str:
        kind = memory.metadata.get("kind")

        if isinstance(kind, str) and kind.strip():
            return kind.strip()

        return "memory"
