from uuid import uuid4

import pytest
from mcp import Client

from agent_platform.adapters.mcp.server import (
    build_mcp_tool_server,
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


class NullObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        pass


@pytest.mark.asyncio
async def test_mcp_server_exposes_registry_schema() -> None:
    run_id = uuid4()

    registry = ToolRegistry(
        [DiagnosticEchoTool()],
        NullObserver(),
    )

    server = build_mcp_tool_server(
        registry,
        run_id_resolver=lambda _: run_id,
    )

    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.list_tools()

    assert len(result.tools) == 1

    tool = result.tools[0]

    assert tool.name == "diagnostic_echo"
    assert tool.input_schema == registry.definitions()[0].input_schema
    assert tool.output_schema == registry.definitions()[0].output_schema


@pytest.mark.asyncio
async def test_mcp_server_routes_call_to_registry() -> None:
    run_id = uuid4()

    registry = ToolRegistry(
        [DiagnosticEchoTool()],
        NullObserver(),
    )

    server = build_mcp_tool_server(
        registry,
        run_id_resolver=lambda _: run_id,
    )

    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "diagnostic_echo",
            {
                "message": "MCP bridge works",
            },
        )

    assert result.is_error is False

    assert result.structured_content == {"message": "MCP bridge works"}
