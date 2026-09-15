from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from agent_platform.adapters.tools.memory import (
    MemoryRecallTool,
    MemoryRememberTool,
)
from agent_platform.domain.memory import (
    MemoryRecord,
    MemoryScope,
    RetrievalAcceptanceDecision,
    RetrievalDecision,
    RetrievalHit,
)
from agent_platform.domain.tool import ToolRequest


class RecordingStore:
    def __init__(self) -> None:
        self.records: list[MemoryRecord] = []

    async def store(
        self,
        record: MemoryRecord,
    ) -> None:
        self.records.append(record)


class StaticRetrieval:
    def __init__(
        self,
        hits: list[RetrievalHit],
    ) -> None:
        self.hits = hits

    async def retrieve(
        self,
        query,
    ) -> list[RetrievalHit]:
        return self.hits


class StaticAcceptance:
    def __init__(
        self,
        decision: RetrievalAcceptanceDecision,
    ) -> None:
        self.decision = decision

    async def evaluate(
        self,
        query,
        hits,
    ) -> RetrievalAcceptanceDecision:
        return self.decision


@pytest.mark.asyncio
async def test_memory_remember_persists_record() -> None:
    store = RecordingStore()

    memory_id = UUID("11111111-1111-1111-1111-111111111111")
    created_at = datetime(
        2026,
        9,
        15,
        12,
        0,
        tzinfo=UTC,
    )

    tool = MemoryRememberTool(
        store,
        id_factory=lambda: memory_id,
        clock=lambda: created_at,
    )

    run_id = uuid4()

    result = await tool.invoke(
        ToolRequest(
            run_id=run_id,
            arguments={
                "namespace": "agent",
                "content": "Local inference uses llama.cpp.",
                "metadata": {
                    "source": "test",
                },
            },
        )
    )

    assert len(store.records) == 1

    memory = store.records[0]

    assert memory.id == memory_id
    assert memory.scope.namespace == "agent"
    assert memory.content == "Local inference uses llama.cpp."
    assert memory.metadata == {
        "source": "test",
    }

    assert result.output == {
        "memory_id": str(memory_id),
        "namespace": "agent",
        "created_at": created_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_memory_recall_returns_memories_on_accept() -> None:
    memory = MemoryRecord(
        id=uuid4(),
        scope=MemoryScope(namespace="agent"),
        content="Local inference uses llama.cpp.",
        created_at=datetime.now(UTC),
        metadata={"source": "test"},
    )

    hit = RetrievalHit(
        memory=memory,
        score=1.0,
        rank=1,
    )

    tool = MemoryRecallTool(
        StaticRetrieval([hit]),
        StaticAcceptance(
            RetrievalAcceptanceDecision(
                decision=RetrievalDecision.ACCEPT,
                reason_code="lexical_evidence",
                metadata={
                    "hit_count": 1,
                },
            )
        ),
    )

    result = await tool.invoke(
        ToolRequest(
            run_id=uuid4(),
            arguments={
                "namespace": "agent",
                "query": "local inference",
            },
        )
    )

    assert result.output["decision"] == "accept"
    assert result.output["reason_code"] == "lexical_evidence"

    memories = result.output["memories"]

    assert len(memories) == 1
    assert memories[0]["content"] == memory.content


@pytest.mark.asyncio
async def test_memory_recall_hides_hits_on_abstain() -> None:
    memory = MemoryRecord(
        id=uuid4(),
        scope=MemoryScope(namespace="agent"),
        content="raw-memory-content",
        created_at=datetime.now(UTC),
    )

    hit = RetrievalHit(
        memory=memory,
        score=1.0,
        rank=1,
    )

    tool = MemoryRecallTool(
        StaticRetrieval([hit]),
        StaticAcceptance(
            RetrievalAcceptanceDecision(
                decision=RetrievalDecision.ABSTAIN,
                reason_code="insufficient_evidence",
            )
        ),
    )

    result = await tool.invoke(
        ToolRequest(
            run_id=uuid4(),
            arguments={
                "namespace": "agent",
                "query": "something",
            },
        )
    )

    assert result.output["decision"] == "abstain"
    assert result.output["memories"] == []
    assert "raw-memory-content" not in str(result.output)


def test_memory_tool_names_are_stable() -> None:
    remember = MemoryRememberTool(RecordingStore())

    recall = MemoryRecallTool(
        StaticRetrieval([]),
        StaticAcceptance(
            RetrievalAcceptanceDecision(
                decision=RetrievalDecision.ABSTAIN,
                reason_code="no_hits",
            )
        ),
    )

    assert remember.definition.name == "memory_remember"
    assert recall.definition.name == "memory_recall"
