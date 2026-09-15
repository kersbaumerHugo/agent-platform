import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from agent_platform.adapters.memory.sqlite import (
    SQLiteFTSRetrieval,
    SQLiteMemoryStore,
)
from agent_platform.domain.memory import (
    MemoryRecord,
    MemoryScope,
    RetrievalQuery,
)


def make_memory(
    namespace: str,
    content: str,
) -> MemoryRecord:
    return MemoryRecord(
        id=uuid4(),
        scope=MemoryScope(namespace=namespace),
        content=content,
        created_at=datetime.now(UTC),
        metadata={"source": "test"},
    )


@pytest.mark.asyncio
async def test_retrieval_returns_matching_memory(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.sqlite3"

    store = SQLiteMemoryStore(database_path)
    retrieval = SQLiteFTSRetrieval(database_path)

    memory = make_memory(
        "agent",
        "The local inference backend uses llama.cpp.",
    )

    await store.store(memory)

    hits = await retrieval.retrieve(
        RetrievalQuery(
            scope=MemoryScope(namespace="agent"),
            text="local inference",
        )
    )

    assert len(hits) == 1
    assert hits[0].memory.id == memory.id
    assert hits[0].rank == 1


@pytest.mark.asyncio
async def test_retrieval_enforces_scope_isolation(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.sqlite3"

    store = SQLiteMemoryStore(database_path)
    retrieval = SQLiteFTSRetrieval(database_path)

    first = make_memory(
        "agent-a",
        "shared diagnostic memory",
    )
    second = make_memory(
        "agent-b",
        "shared diagnostic memory",
    )

    await store.store(first)
    await store.store(second)

    hits = await retrieval.retrieve(
        RetrievalQuery(
            scope=MemoryScope(namespace="agent-a"),
            text="diagnostic memory",
        )
    )

    assert len(hits) == 1
    assert hits[0].memory.id == first.id


@pytest.mark.asyncio
async def test_retrieval_ranks_stronger_match_first(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.sqlite3"

    store = SQLiteMemoryStore(database_path)
    retrieval = SQLiteFTSRetrieval(database_path)

    stronger = make_memory(
        "agent",
        "local local local local",
    )
    weaker = make_memory(
        "agent",
        "local plus several unrelated words about something else",
    )

    await store.store(stronger)
    await store.store(weaker)

    hits = await retrieval.retrieve(
        RetrievalQuery(
            scope=MemoryScope(namespace="agent"),
            text="local",
        )
    )

    assert len(hits) == 2
    assert hits[0].memory.id == stronger.id
    assert hits[0].score >= hits[1].score
    assert [hit.rank for hit in hits] == [1, 2]


@pytest.mark.asyncio
async def test_retrieval_respects_limit(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.sqlite3"

    store = SQLiteMemoryStore(database_path)
    retrieval = SQLiteFTSRetrieval(database_path)

    for index in range(3):
        await store.store(
            make_memory(
                "agent",
                f"memory retrieval example {index}",
            )
        )

    hits = await retrieval.retrieve(
        RetrievalQuery(
            scope=MemoryScope(namespace="agent"),
            text="memory retrieval",
            limit=2,
        )
    )

    assert len(hits) == 2


@pytest.mark.asyncio
async def test_retrieval_returns_empty_for_no_match(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.sqlite3"

    store = SQLiteMemoryStore(database_path)
    retrieval = SQLiteFTSRetrieval(database_path)

    await store.store(
        make_memory(
            "agent",
            "SQLite memory backend",
        )
    )

    hits = await retrieval.retrieve(
        RetrievalQuery(
            scope=MemoryScope(namespace="agent"),
            text="kubernetes",
        )
    )

    assert hits == []


@pytest.mark.asyncio
async def test_retrieval_sanitizes_query_syntax(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.sqlite3"

    store = SQLiteMemoryStore(database_path)
    retrieval = SQLiteFTSRetrieval(database_path)

    memory = make_memory(
        "agent",
        "local inference works",
    )

    await store.store(memory)

    hits = await retrieval.retrieve(
        RetrievalQuery(
            scope=MemoryScope(namespace="agent"),
            text='local inference? "',
        )
    )

    assert len(hits) == 1
    assert hits[0].memory.id == memory.id


@pytest.mark.asyncio
async def test_retrieval_backfills_pre_fts_records(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.sqlite3"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE memory_records (
                id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        memory_id = uuid4()

        connection.execute(
            """
            INSERT INTO memory_records (
                id,
                namespace,
                content,
                created_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(memory_id),
                "agent",
                "legacy persistent memory",
                datetime.now(UTC).isoformat(),
                '{"source":"legacy"}',
            ),
        )

    retrieval = SQLiteFTSRetrieval(database_path)

    hits = await retrieval.retrieve(
        RetrievalQuery(
            scope=MemoryScope(namespace="agent"),
            text="legacy persistent",
        )
    )

    assert len(hits) == 1
    assert hits[0].memory.id == memory_id
