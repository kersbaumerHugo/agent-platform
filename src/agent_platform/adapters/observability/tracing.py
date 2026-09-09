import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import (
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

_configured = False


def _env_bool(
    name: str,
    default: bool,
) -> bool:
    value = os.environ.get(name)

    if value is None:
        return default

    return value.lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


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

    resource = Resource.create(
        {
            SERVICE_NAME: "agent-platform",
            SERVICE_VERSION: "0.0.1",
        }
    )

    provider = TracerProvider(resource=resource)

    if exporter == "console":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    elif exporter == "otlp":
        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "http://127.0.0.1:4317",
        )

        insecure = _env_bool(
            "OTEL_EXPORTER_OTLP_INSECURE",
            True,
        )

        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=endpoint,
                    insecure=insecure,
                )
            )
        )

    else:
        raise ValueError(f"Unsupported trace exporter: {exporter}")

    trace.set_tracer_provider(provider)
    _configured = True
