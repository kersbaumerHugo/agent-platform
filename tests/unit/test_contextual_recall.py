from datetime import UTC, datetime
from uuid import UUID

import pytest

from agent_platform.application.contextual_recall import ContextualRecall
from agent_platform.application.retrieval_acceptance import (
    LexicalRetrievalAcceptanceGate,
)
from agent_platform.domain.context import ContextRef, ContextRole
from agent_platform.domain.memory import (
    MemoryRecord,
    MemoryScope,
    RetrievalDecision,
    RetrievalHit,
    RetrievalQuery,
)


def make_hit(
    *,
    memory_id: str,
    namespace: str,
    content: str,
) -> RetrievalHit:
    return RetrievalHit(
        memory=MemoryRecord(
            id=UUID(memory_id),
            scope=MemoryScope(namespace=namespace),
            content=content,
            created_at=datetime(
                2026,
                9,
                16,
                12,
                0,
                tzinfo=UTC,
            ),
        ),
        score=1.0,
        rank=1,
    )


class RecordingRetrieval:
    def __init__(
        self,
        hits_by_namespace: dict[str, list[RetrievalHit]],
    ) -> None:
        self._hits_by_namespace = hits_by_namespace
        self.queries: list[RetrievalQuery] = []

    async def retrieve(
        self,
        query: RetrievalQuery,
    ) -> list[RetrievalHit]:
        self.queries.append(query)
        return list(
            self._hits_by_namespace.get(
                query.scope.namespace,
                [],
            )
        )


@pytest.mark.asyncio
async def test_recall_queries_only_explicit_contexts_in_declared_order() -> None:
    retrieval = RecordingRetrieval(
        {
            "global": [
                make_hit(
                    memory_id="11111111-1111-1111-1111-111111111111",
                    namespace="global",
                    content="context signal from global memory",
                )
            ],
            "app:linkedin": [
                make_hit(
                    memory_id="22222222-2222-2222-2222-222222222222",
                    namespace="app:linkedin",
                    content="context signal from LinkedIn memory",
                )
            ],
            "project:homelab": [
                make_hit(
                    memory_id="33333333-3333-3333-3333-333333333333",
                    namespace="project:homelab",
                    content="context signal from homelab memory",
                )
            ],
            "project:agent-platform": [
                make_hit(
                    memory_id="44444444-4444-4444-4444-444444444444",
                    namespace="project:agent-platform",
                    content="context signal from Agent Platform memory",
                )
            ],
        }
    )
    recall = ContextualRecall(
        retrieval=retrieval,
        acceptance=LexicalRetrievalAcceptanceGate(),
    )
    contexts = [
        ContextRef(
            role=ContextRole.SHARED,
            namespace="global",
        ),
        ContextRef(
            role=ContextRole.DELIVERY,
            namespace="app:linkedin",
        ),
        ContextRef(
            role=ContextRole.SUBJECT,
            namespace="project:homelab",
        ),
    ]

    results = await recall.recall(
        contexts=contexts,
        text="context signal",
    )

    assert [query.scope.namespace for query in retrieval.queries] == [
        "global",
        "app:linkedin",
        "project:homelab",
    ]
    assert [result.context for result in results] == contexts
    assert all(result.decision.decision is RetrievalDecision.ACCEPT for result in results)
    assert all(len(result.hits) == 1 for result in results)
    assert all(result.context.namespace != "project:agent-platform" for result in results)


@pytest.mark.asyncio
async def test_abstained_scope_does_not_expose_retrieved_hits() -> None:
    retrieval = RecordingRetrieval(
        {
            "app:linkedin": [
                make_hit(
                    memory_id="22222222-2222-2222-2222-222222222222",
                    namespace="app:linkedin",
                    content="unrelated writing preference",
                )
            ]
        }
    )
    recall = ContextualRecall(
        retrieval=retrieval,
        acceptance=LexicalRetrievalAcceptanceGate(),
    )

    results = await recall.recall(
        contexts=[
            ContextRef(
                role=ContextRole.DELIVERY,
                namespace="app:linkedin",
            )
        ],
        text="context signal",
    )

    assert len(results) == 1
    assert results[0].decision.decision is RetrievalDecision.ABSTAIN
    assert results[0].decision.reason_code == "insufficient_query_term_coverage"
    assert results[0].hits == ()


@pytest.mark.asyncio
async def test_scope_mismatch_cannot_cross_context_boundary() -> None:
    retrieval = RecordingRetrieval(
        {
            "project:homelab": [
                make_hit(
                    memory_id="44444444-4444-4444-4444-444444444444",
                    namespace="project:agent-platform",
                    content="context signal",
                )
            ]
        }
    )
    recall = ContextualRecall(
        retrieval=retrieval,
        acceptance=LexicalRetrievalAcceptanceGate(),
    )

    results = await recall.recall(
        contexts=[
            ContextRef(
                role=ContextRole.SUBJECT,
                namespace="project:homelab",
            )
        ],
        text="context signal",
    )

    assert results[0].decision.decision is RetrievalDecision.ABSTAIN
    assert results[0].decision.reason_code == "scope_mismatch"
    assert results[0].hits == ()


@pytest.mark.asyncio
async def test_no_contexts_means_no_memory_retrieval() -> None:
    retrieval = RecordingRetrieval({})
    recall = ContextualRecall(
        retrieval=retrieval,
        acceptance=LexicalRetrievalAcceptanceGate(),
    )

    results = await recall.recall(
        contexts=[],
        text="anything",
    )

    assert results == []
    assert retrieval.queries == []


@pytest.mark.asyncio
async def test_limit_per_context_must_be_positive() -> None:
    recall = ContextualRecall(
        retrieval=RecordingRetrieval({}),
        acceptance=LexicalRetrievalAcceptanceGate(),
    )

    with pytest.raises(
        ValueError,
        match="limit_per_context must be greater than 0",
    ):
        await recall.recall(
            contexts=[],
            text="anything",
            limit_per_context=0,
        )
