import asyncio
import json
import sqlite3
from pathlib import Path

from agent_platform.domain.memory import MemoryRecord


class SQLiteMemoryStore:
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._initialize()

    async def store(self, record: MemoryRecord) -> None:
        await asyncio.to_thread(self._store_sync, record)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)

    def _initialize(self) -> None:
        self._database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_records (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_records_namespace
                ON memory_records(namespace)
                """
            )

    def _store_sync(self, record: MemoryRecord) -> None:
        metadata = record.model_dump(mode="json")["metadata"]

        with self._connect() as connection:
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
                    str(record.id),
                    record.scope.namespace,
                    record.content,
                    record.created_at.isoformat(),
                    json.dumps(
                        metadata,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            )
