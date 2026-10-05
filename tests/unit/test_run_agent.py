from pathlib import Path

import pytest

from agent_platform.adapters.observability.prometheus import (
    PrometheusObserver,
)
from agent_platform.adapters.run_history.sqlite import (
    SQLiteRunHistoryStore,
)
from agent_platform.adapters.runtimes.fake import FakeRuntime
from agent_platform.application.run_agent import RunAgent
from agent_platform.domain.models import (
    RunRequest,
    RunStatus,
    RuntimeRequest,
)

PLATFORM_REVISION = "a" * 40
REPOSITORY_REVISION = "b" * 40


class FailingRuntime:
    @property
    def name(self) -> str:
        return "failing"

    async def execute(
        self,
        request: RuntimeRequest,
    ):
        del request
        raise RuntimeError("runtime boom")


@pytest.mark.asyncio
async def test_run_agent_uses_runtime_contract() -> None:
    service = RunAgent(
        FakeRuntime(),
        PrometheusObserver(),
    )

    result = await service.execute(
        RunRequest(
            agent_id="demo",
            input="hello",
        )
    )

    assert result.status == RunStatus.SUCCEEDED
    assert result.run_id is not None
    assert "[fake-runtime]" in (result.output or "")


@pytest.mark.asyncio
async def test_run_agent_persists_successful_run_history(
    tmp_path: Path,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")
    service = RunAgent(
        FakeRuntime(),
        PrometheusObserver(),
        run_history_store=store,
        platform_revision=PLATFORM_REVISION,
        repository_revision=REPOSITORY_REVISION,
    )

    result = await service.execute(
        RunRequest(
            agent_id="developer-agent",
            input="hello history",
        )
    )

    persisted = store.get(result.run_id)

    assert persisted is not None
    assert persisted.status == RunStatus.SUCCEEDED
    assert persisted.agent_id == "developer-agent"
    assert persisted.runtime == "fake"
    assert persisted.input == "hello history"
    assert persisted.output == result.output
    assert persisted.platform_revision == PLATFORM_REVISION
    assert persisted.repository_revision == REPOSITORY_REVISION
    assert persisted.finished_at is not None
    assert persisted.duration_seconds is not None


@pytest.mark.asyncio
async def test_run_agent_persists_failed_run_history(
    tmp_path: Path,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")
    service = RunAgent(
        FailingRuntime(),
        PrometheusObserver(),
        run_history_store=store,
        platform_revision=PLATFORM_REVISION,
    )

    result = await service.execute(
        RunRequest(
            agent_id="developer-agent",
            input="fail",
        )
    )

    persisted = store.get(result.run_id)

    assert result.status == RunStatus.FAILED
    assert persisted is not None
    assert persisted.status == RunStatus.FAILED
    assert persisted.error == "runtime boom"
    assert persisted.repository_revision is None


def test_run_history_requires_platform_revision(
    tmp_path: Path,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")

    with pytest.raises(
        ValueError,
        match="platform_revision",
    ):
        RunAgent(
            FakeRuntime(),
            PrometheusObserver(),
            run_history_store=store,
        )


def test_run_history_rejects_abbreviated_revision(
    tmp_path: Path,
) -> None:
    store = SQLiteRunHistoryStore(tmp_path / "run-history.sqlite3")

    with pytest.raises(
        ValueError,
        match="platform_revision",
    ):
        RunAgent(
            FakeRuntime(),
            PrometheusObserver(),
            run_history_store=store,
            platform_revision="abc123",
        )


def test_revisions_without_history_store_are_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="require a configured run history store",
    ):
        RunAgent(
            FakeRuntime(),
            PrometheusObserver(),
            platform_revision=PLATFORM_REVISION,
        )
