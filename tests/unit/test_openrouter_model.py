import json
from uuid import uuid4

import httpx
import pytest

from agent_platform.adapters.models.openrouter import OpenRouterModelAdapter
from agent_platform.domain.model import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelToolDefinition,
)


@pytest.mark.asyncio
async def test_openrouter_adapter_maps_platform_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"

        body = json.loads(request.content.decode())

        assert body["model"] == "openrouter/free"
        assert body["messages"] == [
            {
                "role": "user",
                "content": "hello model gateway",
            }
        ]

        return httpx.Response(
            200,
            json={
                "id": "generation-123",
                "model": "example/provider-model",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "hello platform",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 2,
                    "total_tokens": 6,
                },
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as client:
        adapter = OpenRouterModelAdapter(
            api_key="test-key",
            model="openrouter/free",
            client=client,
        )

        result = await adapter.generate(
            ModelRequest(
                run_id=uuid4(),
                messages=[
                    ModelMessage(
                        role=MessageRole.USER,
                        content="hello model gateway",
                    )
                ],
            )
        )

    assert result.provider == "openrouter"
    assert result.model == "example/provider-model"
    assert result.output == "hello platform"
    assert result.provider_request_id == "generation-123"
    assert result.usage is not None
    assert result.usage.total_tokens == 6


@pytest.mark.asyncio
async def test_openrouter_adapter_maps_tool_call() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        body = json.loads(request.content.decode())

        assert body["tools"] == [
            {
                "type": "function",
                "function": {
                    "name": "diagnostic_echo",
                    "description": ("Echo a diagnostic message."),
                    "parameters": {
                        "type": "object",
                        "properties": {"message": {"type": "string"}},
                        "required": ["message"],
                    },
                },
            }
        ]

        return httpx.Response(
            200,
            json={
                "id": "generation-tool-123",
                "model": "example/tool-model",
                "choices": [
                    {
                        "finish_reason": ("tool_calls"),
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-123",
                                    "type": ("function"),
                                    "function": {
                                        "name": ("diagnostic_echo"),
                                        "arguments": ('{"message":"hello"}'),
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                },
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as client:
        adapter = OpenRouterModelAdapter(
            api_key="test-key",
            model="openrouter/free",
            client=client,
        )

        result = await adapter.generate(
            ModelRequest(
                run_id=uuid4(),
                messages=[
                    ModelMessage(
                        role=MessageRole.USER,
                        content=("call the diagnostic tool"),
                    )
                ],
                tools=[
                    ModelToolDefinition(
                        name="diagnostic_echo",
                        description=("Echo a diagnostic message."),
                        input_schema={
                            "type": "object",
                            "properties": {"message": {"type": "string"}},
                            "required": ["message"],
                        },
                    )
                ],
            )
        )

    assert result.output == ""
    assert result.finish_reason == ("tool_calls")

    assert len(result.tool_calls) == 1

    call = result.tool_calls[0]

    assert call.id == "call-123"
    assert call.name == "diagnostic_echo"
    assert call.arguments == ('{"message":"hello"}')
