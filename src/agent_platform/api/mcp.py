from prometheus_client import (
    CONTENT_TYPE_LATEST,
    generate_latest,
)
from starlette.responses import Response

from agent_platform.adapters.mcp.server import (
    build_mcp_tool_server,
)
from agent_platform.adapters.observability.default import (
    default_observer,
)
from agent_platform.adapters.observability.tracing import (
    configure_tracing,
)
from agent_platform.adapters.tools.diagnostic import (
    DiagnosticEchoTool,
)
from agent_platform.application.tool_registry import (
    ToolRegistry,
)

configure_tracing()

registry = ToolRegistry(
    [DiagnosticEchoTool()],
    default_observer,
)

server = build_mcp_tool_server(registry)

app = server.streamable_http_app()


async def metrics(
    request: object,
) -> Response:
    del request

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


app.add_route(
    "/metrics",
    metrics,
    methods=["GET"],
)
