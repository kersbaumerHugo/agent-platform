import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from agent_platform.adapters.memory.sqlite import SQLiteMemoryStore
from agent_platform.domain.memory import MemoryRecord, MemoryScope


def make_memory(
    namespace: str = "test",
    content: str = "Agent Platform memory works.",
) -> MemoryRecord:
    return MemoryRecord(
        id=uuid4(),
        scope=MemoryScope(namespace=namespace),
        content=content,
        created_at=datetime.now(UTC),
        metadata={
            "source": "unit-test",
            "priority": 1,
        },
    )


@pytest.mark.asyncio
async def test_store_persists_memory_record(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.sqlite3"
    store = SQLiteMemoryStore(database_path)
    memory = make_memory()

    await store.store(memory)

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                id,
                namespace,
                content,
                created_at,
                metadata_json
            FROM memory_records
            WHERE id = ?
            """,
            (str(memory.id),),
        ).fetchone()

    assert row is not None

    (
        stored_id,
        namespace,
        content,
        created_at,
        metadata_json,
    ) = row

    assert stored_id == str(memory.id)
    assert namespace == memory.scope.namespace
    assert content == memory.content
    assert created_at == memory.created_at.isoformat()
    assert json.loads(metadata_json) == memory.metadata


@pytest.mark.asyncio
async def test_memory_survives_store_recreation(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.sqlite3"
    memory = make_memory()

    first_store = SQLiteMemoryStore(database_path)
    await first_store.store(memory)

    SQLiteMemoryStore(database_path)

    with sqlite3.connect(database_path) as connection:
        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM memory_records
            WHERE id = ?
            """,
            (str(memory.id),),
        ).fetchone()

    assert count == (1,)


@pytest.mark.asyncio
async def test_store_preserves_scope_isolation_data(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.sqlite3"
    store = SQLiteMemoryStore(database_path)

    first = make_memory(
        namespace="agent-a",
        content="memory A",
    )
    second = make_memory(
        namespace="agent-b",
        content="memory B",
    )

    await store.store(first)
    await store.store(second)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT namespace, content
            FROM memory_records
            ORDER BY namespace
            """
        ).fetchall()

    assert rows == [
        ("agent-a", "memory A"),
        ("agent-b", "memory B"),
    ]


@pytest.mark.asyncio
async def test_duplicate_memory_id_is_rejected(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.sqlite3"
    store = SQLiteMemoryStore(database_path)
    memory = make_memory()

    await store.store(memory)

    with pytest.raises(sqlite3.IntegrityError):
        await store.store(memory)


def test_store_creates_parent_directory(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "agent-platform" / "memory" / "memory.sqlite3"

    SQLiteMemoryStore(database_path)

    assert database_path.is_file()
