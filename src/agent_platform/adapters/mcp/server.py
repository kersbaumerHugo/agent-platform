import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from mcp.server import Server, ServerRequestContext
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
)
from mcp.types import (
    Tool as MCPTool,
)
from starlette.requests import Request

from agent_platform.application.tool_registry import ToolRegistry
from agent_platform.domain.tool import ToolRequest

RUN_ID_HEADER = "x-agent-platform-run-id"

RequestContext = ServerRequestContext[
    dict[str, Any],
    Any,
]

RunIdResolver = Callable[
    [RequestContext],
    UUID,
]


def run_id_from_http_context(
    context: RequestContext,
) -> UUID:
    request = context.request

    if not isinstance(request, Request):
        raise ValueError("MCP request has no HTTP request context.")

    raw_run_id = request.headers.get(RUN_ID_HEADER)

    if raw_run_id is None:
        raise ValueError("MCP request is missing execution context.")

    try:
        return UUID(raw_run_id)
    except ValueError as exc:
        raise ValueError("MCP request has an invalid run id.") from exc


def build_mcp_tool_server(
    registry: ToolRegistry,
    *,
    run_id_resolver: RunIdResolver = (run_id_from_http_context),
) -> Server[dict[str, Any]]:
    async def list_tools(
        context: RequestContext,
        params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        del context, params

        tools = [
            MCPTool(
                name=definition.name,
                description=definition.description,
                input_schema=definition.input_schema,
                output_schema=definition.output_schema,
            )
            for definition in registry.definitions()
        ]

        return ListToolsResult(tools=tools)

    async def call_tool(
        context: RequestContext,
        params: CallToolRequestParams,
    ) -> CallToolResult:
        try:
            run_id = run_id_resolver(context)
        except ValueError:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=("Missing or invalid Agent Platform execution context."),
                    )
                ],
                is_error=True,
            )

        try:
            result = await registry.invoke(
                params.name,
                ToolRequest(
                    run_id=run_id,
                    arguments=dict(params.arguments or {}),
                ),
            )
        except Exception:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text="Tool execution failed.",
                    )
                ],
                is_error=True,
            )

        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(
                        result.output,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                )
            ],
            structured_content=result.output,
        )

    server: Server[dict[str, Any]] = Server(
        "agent-platform-tools",
        version="0.0.1",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )

    return server
