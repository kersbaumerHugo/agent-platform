import os

from opentelemetry import trace
from opentelemetry.sdk.resources import (
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

_configured = False


def configure_tracing() -> None:
    global _configured

    if _configured:
        return

    exporter = os.environ.get(
        "OTEL_TRACES_EXPORTER",
        "none",
    ).lower()

    if exporter == "none":
        return

    if exporter != "console":
        raise ValueError(f"Unsupported trace exporter: {exporter}")

    resource = Resource.create(
        {
            SERVICE_NAME: "agent-platform",
            SERVICE_VERSION: "0.0.1",
        }
    )

    provider = TracerProvider(resource=resource)

    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _configured = True
