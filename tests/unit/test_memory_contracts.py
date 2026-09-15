from datetime import UTC, datetime
from math import nan
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent_platform.domain.memory import (
    MemoryRecord,
    MemoryScope,
    RetrievalAcceptanceDecision,
    RetrievalDecision,
    RetrievalHit,
    RetrievalQuery,
)


def make_memory() -> MemoryRecord:
    return MemoryRecord(
        id=uuid4(),
        scope=MemoryScope(namespace="test"),
        content="The local inference backend uses llama.cpp.",
        created_at=datetime.now(UTC),
    )


def test_memory_record_accepts_explicit_scope_and_aware_timestamp() -> None:
    memory = make_memory()

    assert memory.scope.namespace == "test"
    assert memory.content == "The local inference backend uses llama.cpp."
    assert memory.created_at.tzinfo is not None
    assert memory.metadata == {}


def test_memory_scope_rejects_empty_namespace() -> None:
    with pytest.raises(ValidationError):
        MemoryScope(namespace="")


def test_memory_record_rejects_empty_content() -> None:
    with pytest.raises(ValidationError):
        MemoryRecord(
            id=uuid4(),
            scope=MemoryScope(namespace="test"),
            content="",
            created_at=datetime.now(UTC),
        )


def test_memory_record_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValidationError):
        MemoryRecord(
            id=uuid4(),
            scope=MemoryScope(namespace="test"),
            content="memory",
            created_at=datetime.now(),
        )


def test_retrieval_query_requires_positive_limit() -> None:
    with pytest.raises(ValidationError):
        RetrievalQuery(
            scope=MemoryScope(namespace="test"),
            text="local inference",
            limit=0,
        )


def test_retrieval_hit_requires_positive_rank_and_finite_score() -> None:
    memory = make_memory()

    with pytest.raises(ValidationError):
        RetrievalHit(
            memory=memory,
            score=1.0,
            rank=0,
        )

    with pytest.raises(ValidationError):
        RetrievalHit(
            memory=memory,
            score=nan,
            rank=1,
        )


def test_retrieval_acceptance_supports_accept_and_abstain() -> None:
    accepted = RetrievalAcceptanceDecision(
        decision=RetrievalDecision.ACCEPT,
        reason_code="sufficient_evidence",
    )

    abstained = RetrievalAcceptanceDecision(
        decision=RetrievalDecision.ABSTAIN,
        reason_code="insufficient_evidence",
    )

    assert accepted.decision is RetrievalDecision.ACCEPT
    assert abstained.decision is RetrievalDecision.ABSTAIN
