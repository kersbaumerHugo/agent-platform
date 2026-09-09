import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from agent_platform.adapters.runtimes.fake import FakeRuntime
from agent_platform.application.run_agent import RunAgent
from agent_platform.domain.models import (
    RunRequest,
    RunStatus,
)
from agent_platform.domain.observability import (
    ObservationEvent,
)


class NullObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        pass


@pytest.mark.asyncio
async def test_run_agent_emits_nested_trace_spans() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()

    provider.add_span_processor(SimpleSpanProcessor(exporter))

    tracer = provider.get_tracer("agent-platform-test")

    service = RunAgent(
        FakeRuntime(),
        NullObserver(),
        tracer=tracer,
    )

    result = await service.execute(
        RunRequest(
            agent_id="trace-test",
            input="trace me",
        )
    )

    assert result.status == RunStatus.SUCCEEDED

    spans = exporter.get_finished_spans()

    assert len(spans) == 2

    agent_span = next(span for span in spans if span.name == "agent.run")

    runtime_span = next(span for span in spans if span.name == "runtime.execute")

    assert agent_span.context is not None
    assert runtime_span.parent is not None
    assert runtime_span.parent.span_id == (agent_span.context.span_id)

    assert agent_span.attributes is not None
    assert agent_span.attributes["agent_platform.run.id"] == str(result.run_id)

    assert agent_span.attributes["agent_platform.runtime.name"] == "fake"
