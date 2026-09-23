import sqlite3
from pathlib import Path
from uuid import UUID

from agent_platform.domain.models import RunStatus
from agent_platform.domain.run_history import (
    ModelInvocationRecord,
    RunHistoryCompletion,
    RunHistoryRecord,
    RunHistoryStart,
    ToolInvocationRecord,
)


def _connect(
    database_path: Path,
) -> sqlite3.Connection:
    connection = sqlite3.connect(
        database_path,
        timeout=5.0,
    )
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _initialize_database(
    database_path: Path,
) -> None:
    database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with _connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                platform_revision TEXT NOT NULL
                    CHECK (
                        length(platform_revision) = 40
                        AND platform_revision NOT GLOB '*[^0-9a-f]*'
                    ),
                repository_revision TEXT
                    CHECK (
                        repository_revision IS NULL
                        OR (
                            length(repository_revision) = 40
                            AND repository_revision NOT GLOB '*[^0-9a-f]*'
                        )
                    ),
                runtime TEXT NOT NULL,
                input_text TEXT NOT NULL,
                status TEXT NOT NULL,
                output_text TEXT,
                error_text TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                duration_seconds REAL
                    CHECK (
                        duration_seconds IS NULL
                        OR duration_seconds >= 0
                    )
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS model_invocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                requested_model TEXT NOT NULL,
                resolved_model TEXT,
                status TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                duration_seconds REAL
                    CHECK (
                        duration_seconds IS NULL
                        OR duration_seconds >= 0
                    ),
                prompt_tokens INTEGER
                    CHECK (
                        prompt_tokens IS NULL
                        OR prompt_tokens >= 0
                    ),
                completion_tokens INTEGER
                    CHECK (
                        completion_tokens IS NULL
                        OR completion_tokens >= 0
                    ),
                total_tokens INTEGER
                    CHECK (
                        total_tokens IS NULL
                        OR total_tokens >= 0
                    ),
                error_type TEXT,
                FOREIGN KEY (run_id)
                    REFERENCES runs(run_id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_invocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                status TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                duration_seconds REAL
                    CHECK (
                        duration_seconds IS NULL
                        OR duration_seconds >= 0
                    ),
                error_type TEXT,
                FOREIGN KEY (run_id)
                    REFERENCES runs(run_id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_runs_started_at
            ON runs(started_at DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_runs_agent_id
            ON runs(agent_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_runs_platform_revision
            ON runs(platform_revision)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_runs_repository_revision
            ON runs(repository_revision)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_model_invocations_run_id
            ON model_invocations(run_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tool_invocations_run_id
            ON tool_invocations(run_id)
            """
        )


class SQLiteRunHistoryStore:
    def __init__(
        self,
        database_path: str | Path,
    ) -> None:
        self._database_path = Path(database_path)
        _initialize_database(self._database_path)

    def start_run(
        self,
        record: RunHistoryStart,
    ) -> None:
        with _connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id,
                    agent_id,
                    platform_revision,
                    repository_revision,
                    runtime,
                    input_text,
                    status,
                    output_text,
                    error_text,
                    started_at,
                    finished_at,
                    duration_seconds
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL)
                """,
                (
                    str(record.run_id),
                    record.agent_id,
                    record.platform_revision,
                    record.repository_revision,
                    record.runtime,
                    record.input,
                    RunStatus.RUNNING.value,
                    record.started_at.isoformat(),
                ),
            )

    def finish_run(
        self,
        completion: RunHistoryCompletion,
    ) -> None:
        if completion.status not in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
        }:
            raise ValueError("Run history completion status must be succeeded or failed.")

        with _connect(self._database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE runs
                SET
                    status = ?,
                    output_text = ?,
                    error_text = ?,
                    finished_at = ?,
                    duration_seconds = ?
                WHERE run_id = ?
                """,
                (
                    completion.status.value,
                    completion.output,
                    completion.error,
                    completion.finished_at.isoformat(),
                    completion.duration_seconds,
                    str(completion.run_id),
                ),
            )

            if cursor.rowcount != 1:
                raise ValueError("Run history completion references an unknown run.")

    def append_model_invocation(
        self,
        record: ModelInvocationRecord,
    ) -> None:
        with _connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO model_invocations (
                    run_id,
                    provider,
                    requested_model,
                    resolved_model,
                    status,
                    observed_at,
                    duration_seconds,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    error_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.run_id),
                    record.provider,
                    record.requested_model,
                    record.resolved_model,
                    record.status.value,
                    record.observed_at.isoformat(),
                    record.duration_seconds,
                    record.prompt_tokens,
                    record.completion_tokens,
                    record.total_tokens,
                    record.error_type,
                ),
            )

    def append_tool_invocation(
        self,
        record: ToolInvocationRecord,
    ) -> None:
        with _connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO tool_invocations (
                    run_id,
                    tool_name,
                    status,
                    observed_at,
                    duration_seconds,
                    error_type
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.run_id),
                    record.tool_name,
                    record.status.value,
                    record.observed_at.isoformat(),
                    record.duration_seconds,
                    record.error_type,
                ),
            )

    def get(
        self,
        run_id: UUID,
    ) -> RunHistoryRecord | None:
        with _connect(self._database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT
                    run_id,
                    agent_id,
                    platform_revision,
                    repository_revision,
                    runtime,
                    input_text,
                    status,
                    output_text,
                    error_text,
                    started_at,
                    finished_at,
                    duration_seconds
                FROM runs
                WHERE run_id = ?
                """,
                (str(run_id),),
            ).fetchone()

        if row is None:
            return None

        return self._map_run_row(row)

    def list_recent(
        self,
        *,
        limit: int = 50,
    ) -> tuple[RunHistoryRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be greater than or equal to 1.")

        with _connect(self._database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT
                    run_id,
                    agent_id,
                    platform_revision,
                    repository_revision,
                    runtime,
                    input_text,
                    status,
                    output_text,
                    error_text,
                    started_at,
                    finished_at,
                    duration_seconds
                FROM runs
                ORDER BY
                    started_at DESC,
                    run_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return tuple(self._map_run_row(row) for row in rows)

    def list_model_invocations(
        self,
        run_id: UUID,
    ) -> tuple[ModelInvocationRecord, ...]:
        with _connect(self._database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT
                    run_id,
                    provider,
                    requested_model,
                    resolved_model,
                    status,
                    observed_at,
                    duration_seconds,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    error_type
                FROM model_invocations
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (str(run_id),),
            ).fetchall()

        return tuple(
            ModelInvocationRecord.model_validate(
                {
                    "run_id": row["run_id"],
                    "provider": row["provider"],
                    "requested_model": row["requested_model"],
                    "resolved_model": row["resolved_model"],
                    "status": row["status"],
                    "observed_at": row["observed_at"],
                    "duration_seconds": row["duration_seconds"],
                    "prompt_tokens": row["prompt_tokens"],
                    "completion_tokens": row["completion_tokens"],
                    "total_tokens": row["total_tokens"],
                    "error_type": row["error_type"],
                }
            )
            for row in rows
        )

    def list_tool_invocations(
        self,
        run_id: UUID,
    ) -> tuple[ToolInvocationRecord, ...]:
        with _connect(self._database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT
                    run_id,
                    tool_name,
                    status,
                    observed_at,
                    duration_seconds,
                    error_type
                FROM tool_invocations
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (str(run_id),),
            ).fetchall()

        return tuple(
            ToolInvocationRecord.model_validate(
                {
                    "run_id": row["run_id"],
                    "tool_name": row["tool_name"],
                    "status": row["status"],
                    "observed_at": row["observed_at"],
                    "duration_seconds": row["duration_seconds"],
                    "error_type": row["error_type"],
                }
            )
            for row in rows
        )

    @staticmethod
    def _map_run_row(
        row: sqlite3.Row,
    ) -> RunHistoryRecord:
        return RunHistoryRecord.model_validate(
            {
                "run_id": row["run_id"],
                "agent_id": row["agent_id"],
                "platform_revision": row["platform_revision"],
                "repository_revision": row["repository_revision"],
                "runtime": row["runtime"],
                "input": row["input_text"],
                "status": row["status"],
                "output": row["output_text"],
                "error": row["error_text"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "duration_seconds": row["duration_seconds"],
            }
        )
