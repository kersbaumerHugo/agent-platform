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
