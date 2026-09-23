from pathlib import Path

import pytest

from agent_platform.adapters.run_history.observer import (
    RunHistoryObserver,
)
from agent_platform.api.composition import build_runtime
from agent_platform.api.run_history_composition import (
    build_run_history,
)
from agent_platform.domain.observability import ObservationEvent


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        self.events.append(event)


def test_run_history_is_disabled_without_database_configuration() -> None:
    assert build_run_history({}) is None


def test_run_history_rejects_revision_without_database() -> None:
    with pytest.raises(
        ValueError,
        match="AGENT_PLATFORM_RUN_HISTORY_DB",
    ):
        build_run_history(
            {
                "AGENT_PLATFORM_PLATFORM_REVISION": "a" * 40,
            }
        )


def test_run_history_requires_platform_revision(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="AGENT_PLATFORM_PLATFORM_REVISION",
    ):
        build_run_history(
            {
                "AGENT_PLATFORM_RUN_HISTORY_DB": str(tmp_path / "history.sqlite3"),
            }
        )


def test_run_history_builds_store_with_revisions(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "history.sqlite3"

    result = build_run_history(
        {
            "AGENT_PLATFORM_RUN_HISTORY_DB": str(database_path),
            "AGENT_PLATFORM_PLATFORM_REVISION": "a" * 40,
            "AGENT_PLATFORM_REPOSITORY_REVISION": "b" * 40,
        }
    )

    assert result is not None

    store, platform_revision, repository_revision = result

    assert database_path.is_file()
    assert platform_revision == "a" * 40
    assert repository_revision == "b" * 40

    observer = RunHistoryObserver(store)
    assert observer is not None


def test_tool_calling_runtime_uses_injected_observer(
    tmp_path: Path,
) -> None:
    observer = RecordingObserver()

    runtime = build_runtime(
        {
            "AGENT_PLATFORM_RUNTIME": "tool-calling",
            "MODEL_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_MODEL": "test/model",
            "AGENT_PLATFORM_REPOSITORY_PATH": str(tmp_path),
            "AGENT_PLATFORM_REPOWISE_COMMAND": "python",
        },
        observer=observer,
    )

    assert runtime._gateway._observer is observer
    assert runtime._registry._observer is observer
