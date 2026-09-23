from datetime import UTC, datetime
from uuid import uuid4

from agent_platform.adapters.run_history.observer import (
    RunHistoryObserver,
)
from agent_platform.domain.observability import (
    ObservationComponent,
    ObservationEvent,
    ObservationStatus,
)
from agent_platform.domain.run_history import (
    ModelInvocationRecord,
    ToolInvocationRecord,
)


class RecordingStore:
    def __init__(self) -> None:
        self.models: list[ModelInvocationRecord] = []
        self.tools: list[ToolInvocationRecord] = []

    def append_model_invocation(
        self,
        record: ModelInvocationRecord,
    ) -> None:
        self.models.append(record)

    def append_tool_invocation(
        self,
        record: ToolInvocationRecord,
    ) -> None:
        self.tools.append(record)


def test_observer_ignores_started_events() -> None:
    store = RecordingStore()
    observer = RunHistoryObserver(store)  # type: ignore[arg-type]

    observer.record(
        ObservationEvent(
            run_id=uuid4(),
            component=ObservationComponent.MODEL_GATEWAY,
            event="model.request.started",
            status=ObservationStatus.STARTED,
            provider="local",
            model="qwen3.5-9b-local",
        )
    )

    assert store.models == []
    assert store.tools == []


def test_observer_persists_terminal_model_event() -> None:
    store = RecordingStore()
    observer = RunHistoryObserver(store)  # type: ignore[arg-type]
    run_id = uuid4()
    observed_at = datetime.now(UTC)

    observer.record(
        ObservationEvent(
            run_id=run_id,
            component=ObservationComponent.MODEL_GATEWAY,
            event="model.request.succeeded",
            status=ObservationStatus.SUCCEEDED,
            provider="local",
            model="qwen3.5-9b-local",
            resolved_model="qwen3.5-9b-local",
            observed_at=observed_at,
            duration_seconds=1.25,
            prompt_tokens=100,
            completion_tokens=25,
            total_tokens=125,
        )
    )

    assert len(store.models) == 1
    record = store.models[0]

    assert record.run_id == run_id
    assert record.provider == "local"
    assert record.requested_model == "qwen3.5-9b-local"
    assert record.resolved_model == "qwen3.5-9b-local"
    assert record.total_tokens == 125


def test_observer_persists_terminal_tool_event() -> None:
    store = RecordingStore()
    observer = RunHistoryObserver(store)  # type: ignore[arg-type]
    run_id = uuid4()

    observer.record(
        ObservationEvent(
            run_id=run_id,
            component=ObservationComponent.TOOL,
            event="tool.request.failed",
            status=ObservationStatus.FAILED,
            tool_name="repository_inspect",
            duration_seconds=0.75,
            error_type="RuntimeError",
        )
    )

    assert len(store.tools) == 1
    record = store.tools[0]

    assert record.run_id == run_id
    assert record.tool_name == "repository_inspect"
    assert record.status == ObservationStatus.FAILED
    assert record.error_type == "RuntimeError"
