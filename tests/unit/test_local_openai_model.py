import json
from uuid import uuid4

import httpx
import pytest

from agent_platform.adapters.models.local_openai import (
    LocalOpenAIModelAdapter,
)
from agent_platform.domain.model import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelToolDefinition,
)


@pytest.mark.asyncio
async def test_local_adapter_maps_platform_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "http://192.168.10.40:8080/v1/chat/completions"
        )
        assert request.headers["Authorization"] == "Bearer test-key"

        body = json.loads(request.content.decode())

        assert body["model"] == "qwen3.5-9b-local"
        assert body["chat_template_kwargs"] == {
            "enable_thinking": False,
        }
        assert body["messages"] == [
            {
                "role": "user",
                "content": "hello local inference",
            }
        ]

        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-local-123",
                "model": "qwen3.5-9b-local",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "hello from inference01",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 4,
                    "total_tokens": 9,
                },
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as client:
        adapter = LocalOpenAIModelAdapter(
            api_key="test-key",
            model="qwen3.5-9b-local",
            base_url="http://192.168.10.40:8080/v1",
            client=client,
        )

        result = await adapter.generate(
            ModelRequest(
                run_id=uuid4(),
                messages=[
                    ModelMessage(
                        role=MessageRole.USER,
                        content="hello local inference",
                    )
                ],
            )
        )

    assert result.provider == "local"
    assert result.model == "qwen3.5-9b-local"
    assert result.output == "hello from inference01"
    assert result.finish_reason == "stop"
    assert result.usage is not None
    assert result.usage.total_tokens == 9


@pytest.mark.asyncio
async def test_local_adapter_maps_tool_calls() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())

        assert body["tools"][0]["function"]["name"] == (
            "diagnostic_echo"
        )

        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-tool-123",
                "model": "qwen3.5-9b-local",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-123",
                                    "type": "function",
                                    "function": {
                                        "name": "diagnostic_echo",
                                        "arguments": (
                                            '{"message":"hello"}'
                                        ),
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as client:
        adapter = LocalOpenAIModelAdapter(
            api_key="test-key",
            model="qwen3.5-9b-local",
            base_url="http://192.168.10.40:8080/v1",
            client=client,
        )

        result = await adapter.generate(
            ModelRequest(
                run_id=uuid4(),
                messages=[
                    ModelMessage(
                        role=MessageRole.USER,
                        content="use the diagnostic tool",
                    )
                ],
                tools=[
                    ModelToolDefinition(
                        name="diagnostic_echo",
                        description="Echo a diagnostic message.",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "message": {
                                    "type": "string",
                                }
                            },
                            "required": ["message"],
                        },
                    )
                ],
            )
        )

    assert result.output == ""
    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "diagnostic_echo"
