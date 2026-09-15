import asyncio
import json
import re
import sqlite3
from pathlib import Path

from agent_platform.domain.memory import (
    MemoryRecord,
    RetrievalHit,
    RetrievalQuery,
)

_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


def _connect(database_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(database_path)


def _initialize_database(database_path: Path) -> None:
    database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with _connect(database_path) as connection:
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
        connection.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(
                id UNINDEXED,
                namespace UNINDEXED,
                content,
                tokenize='unicode61'
            )
            """
        )

        # Backfill records created before the FTS index existed.
        connection.execute(
            """
            INSERT INTO memory_fts (
                rowid,
                id,
                namespace,
                content
            )
            SELECT
                records.rowid,
                records.id,
                records.namespace,
                records.content
            FROM memory_records AS records
            WHERE NOT EXISTS (
                SELECT 1
                FROM memory_fts
                WHERE memory_fts.rowid = records.rowid
            )
            """
        )


def _build_match_query(text: str) -> str | None:
    tokens = _TOKEN_PATTERN.findall(text)

    if not tokens:
        return None

    return " AND ".join(f'"{token}"' for token in tokens)


class SQLiteMemoryStore:
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        _initialize_database(self._database_path)

    async def store(self, record: MemoryRecord) -> None:
        await asyncio.to_thread(self._store_sync, record)

    def _store_sync(self, record: MemoryRecord) -> None:
        metadata = record.model_dump(mode="json")["metadata"]

        with _connect(self._database_path) as connection:
            cursor = connection.execute(
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

            rowid = cursor.lastrowid

            if rowid is None:
                raise RuntimeError("SQLite did not return a rowid for the stored memory.")

            connection.execute(
                """
                INSERT INTO memory_fts (
                    rowid,
                    id,
                    namespace,
                    content
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    rowid,
                    str(record.id),
                    record.scope.namespace,
                    record.content,
                ),
            )


class SQLiteFTSRetrieval:
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        _initialize_database(self._database_path)

    async def retrieve(
        self,
        query: RetrievalQuery,
    ) -> list[RetrievalHit]:
        return await asyncio.to_thread(
            self._retrieve_sync,
            query,
        )

    def _retrieve_sync(
        self,
        query: RetrievalQuery,
    ) -> list[RetrievalHit]:
        match_query = _build_match_query(query.text)

        if match_query is None:
            return []

        with _connect(self._database_path) as connection:
            connection.row_factory = sqlite3.Row

            rows = connection.execute(
                """
                SELECT
                    records.id,
                    records.namespace,
                    records.content,
                    records.created_at,
                    records.metadata_json,
                    bm25(memory_fts) AS bm25_score
                FROM memory_fts
                JOIN memory_records AS records
                    ON records.rowid = memory_fts.rowid
                WHERE
                    memory_fts MATCH ?
                    AND memory_fts.namespace = ?
                ORDER BY
                    bm25_score ASC,
                    memory_fts.rowid ASC
                LIMIT ?
                """,
                (
                    match_query,
                    query.scope.namespace,
                    query.limit,
                ),
            ).fetchall()

        hits: list[RetrievalHit] = []

        for rank, row in enumerate(rows, start=1):
            memory = MemoryRecord.model_validate(
                {
                    "id": row["id"],
                    "scope": {
                        "namespace": row["namespace"],
                    },
                    "content": row["content"],
                    "created_at": row["created_at"],
                    "metadata": json.loads(
                        row["metadata_json"],
                    ),
                }
            )

            hits.append(
                RetrievalHit(
                    memory=memory,
                    # SQLite FTS5 BM25 ranks lower values as better.
                    # Negating gives the platform the intuitive
                    # higher-score-is-better convention.
                    score=-float(row["bm25_score"]),
                    rank=rank,
                )
            )

        return hits
