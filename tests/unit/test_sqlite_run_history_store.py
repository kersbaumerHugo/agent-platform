import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from agent_platform.adapters.run_history.sqlite import (
    SQLiteRunHistoryStore,
)
from agent_platform.domain.models import RunStatus
from agent_platform.domain.observability import ObservationStatus
from agent_platform.domain.run_history import (
    ModelInvocationRecord,
    RunHistoryCompletion,
    RunHistoryStart,
    ToolInvocationRecord,
)

PLATFORM_REVISION = "a" * 40
REPOSITORY_REVISION = "b" * 40


def make_start(
    *,
    input_text: str = "Inspect the repository.",
    started_at: datetime | None = None,
) -> RunHistoryStart:
    return RunHistoryStart(
        run_id=uuid4(),
        agent_id="developer-agent",
        platform_revision=PLATFORM_REVISION,
        repository_revision=REPOSITORY_REVISION,
        runtime="tool-calling",
        input=input_text,
        started_at=started_at or datetime.now(UTC),
    )


def make_completion(
    start: RunHistoryStart,
    *,
    status: RunStatus = RunStatus.SUCCEEDED,
) -> RunHistoryCompletion:
    finished = start.started_at + timedelta(seconds=2.5)

    return RunHistoryCompletion(
        run_id=start.run_id,
        status=status,
        output="done" if status == RunStatus.SUCCEEDED else None,
        error="failed" if status == RunStatus.FAILED else None,
        finished_at=finished,
        duration_seconds=2.5,
    )


def test_start_and_finish_run(
    tmp_path: Path,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")
    start = make_start()

    store.start_run(start)

    running = store.get(start.run_id)

    assert running is not None
    assert running.status == RunStatus.RUNNING
    assert running.platform_revision == PLATFORM_REVISION
    assert running.repository_revision == REPOSITORY_REVISION
    assert running.finished_at is None

    store.finish_run(make_completion(start))

    completed = store.get(start.run_id)

    assert completed is not None
    assert completed.status == RunStatus.SUCCEEDED
    assert completed.output == "done"
    assert completed.duration_seconds == 2.5


def test_failed_run_is_preserved(
    tmp_path: Path,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")
    start = make_start()

    store.start_run(start)
    store.finish_run(
        make_completion(
            start,
            status=RunStatus.FAILED,
        )
    )

    completed = store.get(start.run_id)

    assert completed is not None
    assert completed.status == RunStatus.FAILED
    assert completed.output is None
    assert completed.error == "failed"


def test_duplicate_run_id_is_rejected(
    tmp_path: Path,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")
    start = make_start()

    store.start_run(start)

    with pytest.raises(sqlite3.IntegrityError):
        store.start_run(start)


def test_finish_unknown_run_is_rejected(
    tmp_path: Path,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")
    start = make_start()

    with pytest.raises(
        ValueError,
        match="unknown run",
    ):
        store.finish_run(make_completion(start))


def test_non_terminal_completion_is_rejected(
    tmp_path: Path,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")
    start = make_start()

    store.start_run(start)

    completion = RunHistoryCompletion(
        run_id=start.run_id,
        status=RunStatus.RUNNING,
        finished_at=start.started_at + timedelta(seconds=1),
        duration_seconds=1,
    )

    with pytest.raises(
        ValueError,
        match="succeeded or failed",
    ):
        store.finish_run(completion)


def test_model_invocation_is_correlated_by_foreign_key(
    tmp_path: Path,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")
    start = make_start()
    store.start_run(start)

    invocation = ModelInvocationRecord(
        run_id=start.run_id,
        provider="local",
        requested_model="qwen3.5-9b-local",
        resolved_model="qwen3.5-9b-local",
        status=ObservationStatus.SUCCEEDED,
        observed_at=datetime.now(UTC),
        duration_seconds=1.25,
        prompt_tokens=100,
        completion_tokens=25,
        total_tokens=125,
    )

    store.append_model_invocation(invocation)

    assert store.list_model_invocations(start.run_id) == (invocation,)


def test_tool_invocation_is_correlated_by_foreign_key(
    tmp_path: Path,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")
    start = make_start()
    store.start_run(start)

    invocation = ToolInvocationRecord(
        run_id=start.run_id,
        tool_name="repository_inspect",
        status=ObservationStatus.SUCCEEDED,
        observed_at=datetime.now(UTC),
        duration_seconds=0.5,
    )

    store.append_tool_invocation(invocation)

    assert store.list_tool_invocations(start.run_id) == (invocation,)


@pytest.mark.parametrize(
    "kind",
    (
        "model",
        "tool",
    ),
)
def test_child_invocation_without_parent_run_is_rejected(
    tmp_path: Path,
    kind: str,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")
    unknown_run_id = uuid4()

    with pytest.raises(sqlite3.IntegrityError):
        if kind == "model":
            store.append_model_invocation(
                ModelInvocationRecord(
                    run_id=unknown_run_id,
                    provider="local",
                    requested_model="qwen3.5-9b-local",
                    status=ObservationStatus.SUCCEEDED,
                    observed_at=datetime.now(UTC),
                )
            )
        else:
            store.append_tool_invocation(
                ToolInvocationRecord(
                    run_id=unknown_run_id,
                    tool_name="repository_inspect",
                    status=ObservationStatus.SUCCEEDED,
                    observed_at=datetime.now(UTC),
                )
            )


def test_foreign_keys_are_enabled_on_connections(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "run-history.sqlite3"

    SQLiteRunHistoryStore(database_path)

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        enabled = connection.execute("PRAGMA foreign_keys").fetchone()
    finally:
        connection.close()

    assert enabled == (1,)


def test_child_tables_declare_run_foreign_keys(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "run-history.sqlite3"

    SQLiteRunHistoryStore(database_path)

    with sqlite3.connect(database_path) as connection:
        model_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(model_invocations)"
        ).fetchall()
        tool_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(tool_invocations)"
        ).fetchall()

    assert any(
        row[2] == "runs" and row[3] == "run_id" and row[4] == "run_id" for row in model_foreign_keys
    )
    assert any(
        row[2] == "runs" and row[3] == "run_id" and row[4] == "run_id" for row in tool_foreign_keys
    )


def test_list_recent_returns_newest_first(
    tmp_path: Path,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")
    base = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)

    oldest = make_start(
        input_text="oldest",
        started_at=base,
    )
    middle = make_start(
        input_text="middle",
        started_at=base + timedelta(minutes=1),
    )
    newest = make_start(
        input_text="newest",
        started_at=base + timedelta(minutes=2),
    )

    for record in (oldest, newest, middle):
        store.start_run(record)

    recent = store.list_recent(limit=2)

    assert [record.input for record in recent] == [
        "newest",
        "middle",
    ]


def test_list_recent_rejects_non_positive_limit(
    tmp_path: Path,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")

    with pytest.raises(
        ValueError,
        match="greater than or equal to 1",
    ):
        store.list_recent(limit=0)


def test_revision_must_be_full_lowercase_sha() -> None:
    with pytest.raises(ValueError):
        RunHistoryStart(
            run_id=uuid4(),
            agent_id="developer-agent",
            platform_revision="abc123",
            runtime="tool-calling",
            input="test",
            started_at=datetime.now(UTC),
        )


def test_store_creates_parent_directory(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "agent-platform" / "history" / "run-history.sqlite3"

    SQLiteRunHistoryStore(database_path)

    assert database_path.is_file()
