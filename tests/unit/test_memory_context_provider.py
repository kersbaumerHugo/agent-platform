from datetime import UTC, datetime
from uuid import UUID

import pytest

from agent_platform.adapters.memory.context_provider import (
    MemoryContextProvider,
)
from agent_platform.contracts.context import ContextProviderContract
from agent_platform.domain.context import (
    ContextRef,
    ContextRole,
    content_sha256,
)
from agent_platform.domain.context_preparation import RecallRequest
from agent_platform.domain.memory import (
    MemoryRecord,
    MemoryScope,
    RetrievalAcceptanceDecision,
    RetrievalDecision,
    RetrievalHit,
    RetrievalQuery,
)


def make_memory(
    *,
    memory_id: str,
    namespace: str = "project:homelab",
    content: str = "homelab observability baseline",
    metadata: dict[str, object] | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        id=UUID(memory_id),
        scope=MemoryScope(
            namespace=namespace,
        ),
        content=content,
        created_at=datetime(
            2026,
            9,
            16,
            12,
            0,
            tzinfo=UTC,
        ),
        metadata=metadata or {},
    )


def make_hit(
    *,
    memory_id: str,
    namespace: str = "project:homelab",
    content: str = "homelab observability baseline",
    metadata: dict[str, object] | None = None,
    rank: int = 1,
    score: float = 1.0,
) -> RetrievalHit:
    return RetrievalHit(
        memory=make_memory(
            memory_id=memory_id,
            namespace=namespace,
            content=content,
            metadata=metadata,
        ),
        score=score,
        rank=rank,
    )


def make_request(
    *,
    namespace: str = "project:homelab",
    query: str = "homelab observability",
    limit: int = 3,
) -> RecallRequest:
    return RecallRequest(
        request_id="subject",
        context=ContextRef(
            role=ContextRole.SUBJECT,
            namespace=namespace,
        ),
        query=query,
        limit=limit,
    )


class RecordingRetrieval:
    def __init__(
        self,
        hits: list[RetrievalHit],
    ) -> None:
        self._hits = hits
        self.queries: list[RetrievalQuery] = []

    async def retrieve(
        self,
        query: RetrievalQuery,
    ) -> list[RetrievalHit]:
        self.queries.append(query)
        return list(self._hits)


class RecordingAcceptance:
    def __init__(
        self,
        decision: RetrievalDecision,
    ) -> None:
        self._decision = decision
        self.calls: list[tuple[RetrievalQuery, tuple[RetrievalHit, ...]]] = []

    async def evaluate(
        self,
        query: RetrievalQuery,
        hits: list[RetrievalHit],
    ) -> RetrievalAcceptanceDecision:
        self.calls.append(
            (
                query,
                tuple(hits),
            )
        )
        return RetrievalAcceptanceDecision(
            decision=self._decision,
            reason_code=("accepted" if self._decision is RetrievalDecision.ACCEPT else "rejected"),
        )


def assert_context_provider_contract(
    provider: ContextProviderContract,
) -> None:
    assert provider.name


def test_memory_provider_satisfies_context_provider_contract() -> None:
    provider = MemoryContextProvider(
        retrieval=RecordingRetrieval([]),
        acceptance=RecordingAcceptance(
            RetrievalDecision.ABSTAIN,
        ),
    )

    assert_context_provider_contract(provider)


@pytest.mark.asyncio
async def test_provider_translates_recall_request_to_retrieval_query() -> None:
    retrieval = RecordingRetrieval([])
    acceptance = RecordingAcceptance(
        RetrievalDecision.ABSTAIN,
    )
    provider = MemoryContextProvider(
        retrieval=retrieval,
        acceptance=acceptance,
    )

    contribution = await provider.provide(
        make_request(
            namespace="project:homelab",
            query="homelab observability",
            limit=7,
        )
    )

    assert len(retrieval.queries) == 1
    query = retrieval.queries[0]
    assert query.scope.namespace == "project:homelab"
    assert query.text == "homelab observability"
    assert query.limit == 7
    assert contribution.context.namespace == "project:homelab"
    assert contribution.items == ()


@pytest.mark.asyncio
async def test_accepted_memory_becomes_source_neutral_context_item() -> None:
    memory_id = "11111111-1111-1111-1111-111111111111"
    content = "homelab observability baseline"
    retrieval = RecordingRetrieval(
        [
            make_hit(
                memory_id=memory_id,
                content=content,
                metadata={
                    "kind": "decision",
                },
                score=-12.5,
            )
        ]
    )
    provider = MemoryContextProvider(
        retrieval=retrieval,
        acceptance=RecordingAcceptance(
            RetrievalDecision.ACCEPT,
        ),
    )

    contribution = await provider.provide(make_request())

    assert contribution.provider == "memory"
    assert len(contribution.items) == 1

    item = contribution.items[0]
    assert item.item_id == f"memory:{memory_id}"
    assert item.content == content
    assert item.kind == "decision"
    assert item.provenance.provider == "memory"
    assert item.provenance.source_id == memory_id
    assert item.provenance.source_revision is None
    assert item.provenance.content_hash == content_sha256(content)

    dumped = contribution.model_dump()
    assert "score" not in str(dumped)
    assert "rank" not in str(dumped)


@pytest.mark.asyncio
async def test_memory_kind_defaults_when_metadata_kind_is_missing() -> None:
    provider = MemoryContextProvider(
        retrieval=RecordingRetrieval(
            [
                make_hit(
                    memory_id=("11111111-1111-1111-1111-111111111111"),
                )
            ]
        ),
        acceptance=RecordingAcceptance(
            RetrievalDecision.ACCEPT,
        ),
    )

    contribution = await provider.provide(make_request())

    assert contribution.items[0].kind == "memory"


@pytest.mark.asyncio
async def test_provider_orders_accepted_items_by_rank_then_source_id() -> None:
    provider = MemoryContextProvider(
        retrieval=RecordingRetrieval(
            [
                make_hit(
                    memory_id=("33333333-3333-3333-3333-333333333333"),
                    content="third",
                    rank=2,
                ),
                make_hit(
                    memory_id=("22222222-2222-2222-2222-222222222222"),
                    content="second",
                    rank=1,
                ),
                make_hit(
                    memory_id=("11111111-1111-1111-1111-111111111111"),
                    content="first",
                    rank=1,
                ),
            ]
        ),
        acceptance=RecordingAcceptance(
            RetrievalDecision.ACCEPT,
        ),
    )

    contribution = await provider.provide(make_request())

    assert [item.provenance.source_id for item in contribution.items] == [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
    ]


@pytest.mark.asyncio
async def test_abstain_exposes_no_retrieved_memory() -> None:
    provider = MemoryContextProvider(
        retrieval=RecordingRetrieval(
            [
                make_hit(
                    memory_id=("11111111-1111-1111-1111-111111111111"),
                )
            ]
        ),
        acceptance=RecordingAcceptance(
            RetrievalDecision.ABSTAIN,
        ),
    )

    contribution = await provider.provide(make_request())

    assert contribution.provider == "memory"
    assert contribution.items == ()


@pytest.mark.asyncio
async def test_scope_mismatch_fails_closed_even_if_gate_accepts() -> None:
    provider = MemoryContextProvider(
        retrieval=RecordingRetrieval(
            [
                make_hit(
                    memory_id=("11111111-1111-1111-1111-111111111111"),
                    namespace="project:agent-platform",
                )
            ]
        ),
        acceptance=RecordingAcceptance(
            RetrievalDecision.ACCEPT,
        ),
    )

    contribution = await provider.provide(
        make_request(
            namespace="project:homelab",
        )
    )

    assert contribution.items == ()
