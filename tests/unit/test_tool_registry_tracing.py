from uuid import uuid4

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

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


class NullObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        pass


@pytest.mark.asyncio
async def test_tool_registry_emits_trace_span() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()

    provider.add_span_processor(SimpleSpanProcessor(exporter))

    tracer = provider.get_tracer("agent-platform-tool-test")

    registry = ToolRegistry(
        [DiagnosticEchoTool()],
        NullObserver(),
        tracer=tracer,
    )

    run_id = uuid4()

    await registry.invoke(
        "diagnostic_echo",
        ToolRequest(
            run_id=run_id,
            arguments={
                "message": "trace me",
            },
        ),
    )

    spans = exporter.get_finished_spans()

    assert len(spans) == 1

    span = spans[0]

    assert span.name == "tool.invoke"
    assert span.attributes is not None

    assert span.attributes["agent_platform.run.id"] == str(run_id)

    assert span.attributes["agent_platform.tool.name"] == "diagnostic_echo"

    assert span.attributes["agent_platform.tool.status"] == "succeeded"
