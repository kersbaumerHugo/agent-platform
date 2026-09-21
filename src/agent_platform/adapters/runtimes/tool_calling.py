from __future__ import annotations

import json
from typing import Protocol

from agent_platform.application.tool_registry import ToolRegistry
from agent_platform.domain.model import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelResult,
    ModelToolCall,
    ModelToolDefinition,
)
from agent_platform.domain.models import (
    RuntimeRequest,
    RuntimeResult,
)
from agent_platform.domain.tool import (
    ToolRequest,
    ToolResult,
)


class _ModelGatewayContract(Protocol):
    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult: ...


class ToolCallingRuntime:
    """Bounded runtime that executes one model tool-call round."""

    def __init__(
        self,
        *,
        gateway: _ModelGatewayContract,
        registry: ToolRegistry,
        principal_id: str,
    ) -> None:
        normalized_principal = principal_id.strip()

        if not normalized_principal:
            raise ValueError("Tool-calling runtime principal_id must not be blank.")

        self._gateway = gateway
        self._registry = registry
        self._principal_id = normalized_principal

    @property
    def name(self) -> str:
        return "tool-calling"

    async def execute(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResult:
        tools = [
            ModelToolDefinition(
                name=definition.name,
                description=definition.description,
                input_schema=definition.input_schema,
            )
            for definition in self._registry.definitions()
        ]

        messages = [
            ModelMessage(
                role=MessageRole.USER,
                content=request.input,
            )
        ]

        first = await self._gateway.generate(
            ModelRequest(
                run_id=request.run_id,
                messages=messages,
                tools=tools,
            )
        )

        if not first.tool_calls:
            return RuntimeResult(output=self._require_final_output(first))

        messages.append(
            ModelMessage(
                role=MessageRole.ASSISTANT,
                content=first.output or None,
                tool_calls=first.tool_calls,
            )
        )

        for tool_call in first.tool_calls:
            tool_result = await self._invoke_tool(
                request,
                tool_call,
            )

            messages.append(
                ModelMessage(
                    role=MessageRole.TOOL,
                    content=json.dumps(
                        tool_result.output,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    tool_call_id=tool_call.id,
                )
            )

        final = await self._gateway.generate(
            ModelRequest(
                run_id=request.run_id,
                messages=messages,
                tools=[],
                max_tokens=512,
            )
        )

        if final.tool_calls:
            raise RuntimeError("Tool-calling runtime exceeded the V0 one-round tool-call limit.")

        return RuntimeResult(output=self._require_final_output(final))

    async def _invoke_tool(
        self,
        request: RuntimeRequest,
        tool_call: ModelToolCall,
    ) -> ToolResult:
        try:
            arguments = json.loads(tool_call.arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Tool call {tool_call.id} contains invalid JSON arguments.") from exc

        if not isinstance(arguments, dict):
            raise ValueError(f"Tool call {tool_call.id} arguments must be a JSON object.")

        return await self._registry.invoke(
            tool_call.name,
            ToolRequest(
                run_id=request.run_id,
                principal_id=self._principal_id,
                arguments=arguments,
            ),
        )

    @staticmethod
    def _require_final_output(
        result: ModelResult,
    ) -> str:
        output = result.output.strip()

        if not output:
            raise RuntimeError("Model completed without final output.")

        return output
