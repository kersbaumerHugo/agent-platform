from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_platform.application.retrieval_acceptance import (
    LexicalRetrievalAcceptanceGate,
)
from agent_platform.domain.memory import (
    MemoryRecord,
    MemoryScope,
    RetrievalDecision,
    RetrievalHit,
    RetrievalQuery,
)


def make_hit(
    *,
    namespace: str = "agent",
    content: str = "local inference uses llama cpp",
    score: float = 1.0,
    rank: int = 1,
) -> RetrievalHit:
    return RetrievalHit(
        memory=MemoryRecord(
            id=uuid4(),
            scope=MemoryScope(namespace=namespace),
            content=content,
            created_at=datetime.now(UTC),
        ),
        score=score,
        rank=rank,
    )


@pytest.mark.asyncio
async def test_accepts_sufficient_lexical_evidence() -> None:
    gate = LexicalRetrievalAcceptanceGate()

    decision = await gate.evaluate(
        RetrievalQuery(
            scope=MemoryScope(namespace="agent"),
            text="local inference",
        ),
        [
            make_hit(
                content="The local inference backend works.",
            )
        ],
    )

    assert decision.decision is RetrievalDecision.ACCEPT
    assert decision.reason_code == "lexical_evidence"
    assert decision.metadata["query_term_coverage"] == 1.0


@pytest.mark.asyncio
async def test_abstains_when_there_are_no_hits() -> None:
    gate = LexicalRetrievalAcceptanceGate()

    decision = await gate.evaluate(
        RetrievalQuery(
            scope=MemoryScope(namespace="agent"),
            text="kubernetes",
        ),
        [],
    )

    assert decision.decision is RetrievalDecision.ABSTAIN
    assert decision.reason_code == "no_hits"


@pytest.mark.asyncio
async def test_abstains_on_insufficient_term_coverage() -> None:
    gate = LexicalRetrievalAcceptanceGate()

    decision = await gate.evaluate(
        RetrievalQuery(
            scope=MemoryScope(namespace="agent"),
            text="local inference backend",
        ),
        [
            make_hit(
                content="local inference",
            )
        ],
    )

    assert decision.decision is RetrievalDecision.ABSTAIN
    assert decision.reason_code == "insufficient_query_term_coverage"
    assert decision.metadata["query_term_coverage"] < 1.0


@pytest.mark.asyncio
async def test_abstains_on_scope_mismatch() -> None:
    gate = LexicalRetrievalAcceptanceGate()

    decision = await gate.evaluate(
        RetrievalQuery(
            scope=MemoryScope(namespace="agent-a"),
            text="local inference",
        ),
        [
            make_hit(
                namespace="agent-b",
                content="local inference",
            )
        ],
    )

    assert decision.decision is RetrievalDecision.ABSTAIN
    assert decision.reason_code == "scope_mismatch"


@pytest.mark.asyncio
async def test_matching_is_case_and_punctuation_insensitive() -> None:
    gate = LexicalRetrievalAcceptanceGate()

    decision = await gate.evaluate(
        RetrievalQuery(
            scope=MemoryScope(namespace="agent"),
            text="LOCAL inference!",
        ),
        [
            make_hit(
                content="Local inference works.",
            )
        ],
    )

    assert decision.decision is RetrievalDecision.ACCEPT


@pytest.mark.asyncio
async def test_decision_metadata_does_not_expose_memory_content() -> None:
    gate = LexicalRetrievalAcceptanceGate()

    decision = await gate.evaluate(
        RetrievalQuery(
            scope=MemoryScope(namespace="agent"),
            text="secret value",
        ),
        [
            make_hit(
                content="secret value raw-memory-content",
            )
        ],
    )

    serialized = decision.model_dump_json()

    assert "raw-memory-content" not in serialized


def test_rejects_invalid_coverage_configuration() -> None:
    with pytest.raises(ValueError):
        LexicalRetrievalAcceptanceGate(
            min_query_term_coverage=0,
        )

    with pytest.raises(ValueError):
        LexicalRetrievalAcceptanceGate(
            min_query_term_coverage=1.1,
        )
