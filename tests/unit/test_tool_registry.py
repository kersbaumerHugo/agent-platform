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
from agent_platform.domain.tool import (
    ToolDefinition,
    ToolRequest,
    ToolResult,
)


class KeyErrorTool:
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="key_error_tool",
            description="Raise an internal KeyError for testing.",
            input_schema={},
            output_schema={},
        )

    async def invoke(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        del request
        raise KeyError("tool-internal-missing-key")


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
    observer = RecordingObserver()
    registry = ToolRegistry(
        [],
        observer,
    )
    run_id = uuid4()

    with pytest.raises(
        KeyError,
        match="Unknown tool: missing",
    ):
        await registry.invoke(
            "missing",
            ToolRequest(
                run_id=run_id,
            ),
        )

    assert [event.event for event in observer.events] == [
        "tool.request.started",
        "tool.request.failed",
    ]

    failed = observer.events[-1]

    assert failed.run_id == run_id
    assert failed.status is ObservationStatus.FAILED
    assert failed.tool_name == "missing"
    assert failed.error_type == "KeyError"
    assert failed.duration_seconds is not None


@pytest.mark.asyncio
async def test_registered_tool_key_error_preserves_original_semantics() -> None:
    observer = RecordingObserver()
    registry = ToolRegistry(
        [KeyErrorTool()],
        observer,
    )

    with pytest.raises(
        KeyError,
        match="tool-internal-missing-key",
    ) as exc_info:
        await registry.invoke(
            "key_error_tool",
            ToolRequest(
                run_id=uuid4(),
            ),
        )

    assert "Unknown tool" not in str(exc_info.value)

    assert [event.event for event in observer.events] == [
        "tool.request.started",
        "tool.request.failed",
    ]

    failed = observer.events[-1]

    assert failed.status is ObservationStatus.FAILED
    assert failed.tool_name == "key_error_tool"
    assert failed.error_type == "KeyError"
