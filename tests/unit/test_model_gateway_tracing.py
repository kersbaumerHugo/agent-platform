from uuid import uuid4

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from agent_platform.application.model_gateway import (
    ModelGateway,
)
from agent_platform.domain.model import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelResult,
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


class TracedFakeModel:
    provider = "fake-provider"
    model = "fake-model"

    def __init__(self, tracer) -> None:
        self._tracer = tracer

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        with self._tracer.start_as_current_span("provider.fake"):
            return ModelResult(
                provider=self.provider,
                model="resolved-model",
                output="traced",
            )


@pytest.mark.asyncio
async def test_model_gateway_emits_nested_provider_span() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()

    provider.add_span_processor(SimpleSpanProcessor(exporter))

    tracer = provider.get_tracer("agent-platform-model-test")

    gateway = ModelGateway(
        TracedFakeModel(tracer),
        NullObserver(),
        tracer=tracer,
    )

    run_id = uuid4()

    result = await gateway.generate(
        ModelRequest(
            run_id=run_id,
            messages=[
                ModelMessage(
                    role=MessageRole.USER,
                    content="trace model",
                )
            ],
        )
    )

    assert result.output == "traced"

    spans = exporter.get_finished_spans()

    assert len(spans) == 2

    gateway_span = next(span for span in spans if span.name == "model.gateway")

    provider_span = next(span for span in spans if span.name == "provider.fake")

    assert gateway_span.context is not None
    assert provider_span.parent is not None

    assert provider_span.parent.span_id == (gateway_span.context.span_id)

    assert gateway_span.attributes is not None
    assert gateway_span.attributes["agent_platform.run.id"] == str(run_id)
