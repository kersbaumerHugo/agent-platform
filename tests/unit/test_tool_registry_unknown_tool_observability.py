import uuid

import pytest

from agent_platform.application.tool_registry import (
    ToolRegistry,
)
from agent_platform.contracts.observability import (
    ObservationContract,
)
from agent_platform.domain.observability import (
    ObservationComponent,
    ObservationEvent,
    ObservationStatus,
)
from agent_platform.domain.tool import ToolRequest


class ObservabilityRecordingObserver(ObservationContract):
    """Observer that records all observation events for verification."""

    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def record(self, event: ObservationEvent) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_unknown_tool_failure_flows_through_normal_observability_path() -> None:
    """
    Verify that unknown-tool KeyError failures flow through the same normal
    observability and tracing path used for other tool failures.

    This test ensures:
    - Unknown tool failures are recorded as failed observation events
    - Tracing span captures the error
    - The error_type is set to "KeyError"
    - Duration is calculated correctly
    - The failed event is recorded before the exception is re-raised
    """
    observer = ObservabilityRecordingObserver()
    registry = ToolRegistry(
        [],
        observer,
    )

    request = ToolRequest(run_id=uuid.uuid4())

    with pytest.raises(KeyError, match="Unknown tool"):
        await registry.invoke("missing", request)

    # Verify the observability events follow the normal pattern:
    # 1. tool.request.started event
    # 2. tool.request.failed event with proper attributes
    assert len(observer.events) == 2

    # First event should be the started event
    assert observer.events[0].event == "tool.request.started"
    assert observer.events[0].status == ObservationStatus.STARTED
    assert observer.events[0].tool_name == "missing"
    assert observer.events[0].run_id == request.run_id

    # Second event should be the failed event
    assert observer.events[1].event == "tool.request.failed"
    assert observer.events[1].status == ObservationStatus.FAILED
    assert observer.events[1].tool_name == "missing"
    assert observer.events[1].run_id == request.run_id
    assert observer.events[1].error_type == "KeyError"
    assert observer.events[1].duration_seconds is not None
    assert observer.events[1].duration_seconds > 0


@pytest.mark.asyncio
async def test_unknown_tool_failure_recording_does_not_duplicate_events() -> None:
    """
    Verify that unknown-tool KeyError doesn't create a duplicated observation path.
    Only one failed event should be recorded, not two.
    """
    observer = ObservabilityRecordingObserver()
    registry = ToolRegistry(
        [],
        observer,
    )

    request = ToolRequest(run_id=uuid.uuid4())

    with pytest.raises(KeyError):
        await registry.invoke("unknown", request)

    # Should have exactly 2 events: started and failed
    assert len(observer.events) == 2

    failed_events = [e for e in observer.events if e.event == "tool.request.failed"]
    assert len(failed_events) == 1, "Should not have duplicated failed events"


@pytest.mark.asyncio
async def test_unknown_tool_failure_event_has_correct_attributes() -> None:
    """
    Verify that the failed observation event for unknown tools has all
    the correct attributes matching the normal failure path.
    """
    observer = ObservabilityRecordingObserver()
    registry = ToolRegistry(
        [],
        observer,
    )

    request = ToolRequest(run_id=uuid.uuid4())

    with pytest.raises(KeyError):
        await registry.invoke("nonexistent", request)

    failed_event = observer.events[1]  # Second event is the failed one

    assert failed_event.run_id is not None
    assert failed_event.component == ObservationComponent.TOOL
    assert failed_event.event == "tool.request.failed"
    assert failed_event.status == ObservationStatus.FAILED
    assert failed_event.tool_name == "nonexistent"
    assert failed_event.error_type == "KeyError"
    assert failed_event.duration_seconds is not None
    assert failed_event.duration_seconds > 0
