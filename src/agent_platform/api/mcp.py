import os
from pathlib import Path

from mcp.server.transport_security import (
    TransportSecuritySettings,
)
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    generate_latest,
)
from starlette.responses import Response

from agent_platform.adapters.mcp.server import (
    build_mcp_tool_server,
)
from agent_platform.adapters.memory.sqlite import (
    SQLiteFTSRetrieval,
    SQLiteMemoryStore,
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
from agent_platform.adapters.tools.memory import (
    MemoryRecallTool,
    MemoryRememberTool,
)
from agent_platform.application.retrieval_acceptance import (
    LexicalRetrievalAcceptanceGate,
)
from agent_platform.application.tool_registry import (
    ToolRegistry,
)
from agent_platform.contracts.tool import ToolContract


def build_transport_security() -> TransportSecuritySettings:
    allowed_hosts = [
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
    ]

    remote_host = os.getenv("AGENT_PLATFORM_MCP_ALLOWED_HOST")

    if remote_host:
        allowed_hosts.append(remote_host)

    return TransportSecuritySettings(
        allowed_hosts=allowed_hosts,
    )


def build_tool_registry(
    memory_database_path: str | Path | None = None,
) -> ToolRegistry:
    tools: list[ToolContract] = [
        DiagnosticEchoTool(),
    ]

    if memory_database_path is not None:
        store = SQLiteMemoryStore(
            memory_database_path,
        )
        retrieval = SQLiteFTSRetrieval(
            memory_database_path,
        )
        acceptance = LexicalRetrievalAcceptanceGate()

        tools.extend(
            [
                MemoryRememberTool(store),
                MemoryRecallTool(
                    retrieval,
                    acceptance,
                ),
            ]
        )

    return ToolRegistry(
        tools,
        default_observer,
    )


configure_tracing()

registry = build_tool_registry(os.getenv("AGENT_PLATFORM_MEMORY_DB"))

server = build_mcp_tool_server(registry)

app = server.streamable_http_app(
    transport_security=build_transport_security(),
)


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
