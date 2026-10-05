from uuid import uuid4

import pytest

from agent_platform.adapters.tools.diagnostic import (
    DiagnosticEchoTool,
)
from agent_platform.application.tool_registry import (
    ToolRegistry,
)
from agent_platform.domain.observability import (
    ObservationEvent,
    ObservationStatus,
)
from agent_platform.domain.tool import ToolRequest


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        self.events.append(event)


def test_registry_exposes_registered_tool() -> None:
    registry = ToolRegistry(
        [DiagnosticEchoTool()],
        RecordingObserver(),
    )

    definitions = registry.definitions()

    assert len(definitions) == 1
    assert definitions[0].name == "diagnostic_echo"


@pytest.mark.asyncio
async def test_registry_invokes_tool() -> None:
    observer = RecordingObserver()

    registry = ToolRegistry(
        [DiagnosticEchoTool()],
        observer,
    )

    run_id = uuid4()

    result = await registry.invoke(
        "diagnostic_echo",
        ToolRequest(
            run_id=run_id,
            arguments={
                "message": "tool layer works",
            },
        ),
    )

    assert result.run_id == run_id
    assert result.tool_name == "diagnostic_echo"
    assert result.output == {"message": "tool layer works"}

    assert [event.event for event in observer.events] == [
        "tool.request.started",
        "tool.request.succeeded",
    ]

    assert all(event.run_id == run_id for event in observer.events)


def test_registry_rejects_duplicate_tool() -> None:
    registry = ToolRegistry(
        [DiagnosticEchoTool()],
        RecordingObserver(),
    )

    with pytest.raises(
        ValueError,
        match="Tool already registered",
    ):
        registry.register(DiagnosticEchoTool())


@pytest.mark.asyncio
async def test_registry_rejects_unknown_tool() -> None:
    registry = ToolRegistry(
        [],
        RecordingObserver(),
    )

    with pytest.raises(
        KeyError,
        match="Unknown tool",
    ):
        await registry.invoke(
            "missing",
            ToolRequest(
                run_id=uuid4(),
            ),
        )


@pytest.mark.asyncio
async def test_registry_observability_on_unknown_tool() -> None:
    """Test that unknown tool invocations are observed before raising KeyError."""
    observer = RecordingObserver()
    registry = ToolRegistry(
        [],
        observer,
    )

    run_id = uuid4()

    with pytest.raises(KeyError, match="Unknown tool") as exc_info:
        await registry.invoke(
            "missing",
            ToolRequest(
                run_id=run_id,
            ),
        )

    # Verify KeyError was raised
    assert "Unknown tool: missing" in str(exc_info.value)

    # Verify observation events were recorded
    assert len(observer.events) == 2

    # First event should be started
    assert observer.events[0].event == "tool.request.started"
    assert observer.events[0].status == ObservationStatus.STARTED
    assert observer.events[0].tool_name == "missing"

    # Second event should be failed
    assert observer.events[1].event == "tool.request.failed"
    assert observer.events[1].status == ObservationStatus.FAILED
    assert observer.events[1].tool_name == "missing"
    assert observer.events[1].error_type == "KeyError"

    # Both events should have the same run_id
    assert observer.events[0].run_id == run_id
    assert observer.events[1].run_id == run_id
