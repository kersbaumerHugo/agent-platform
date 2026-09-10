import json
from uuid import UUID

from fastapi.testclient import TestClient

from agent_platform.api.main import app
from agent_platform.api.openai_compat import (
    OpenAICompatMessage,
    get_model_gateway,
    map_messages,
    stream_result,
)
from agent_platform.application.model_gateway import ModelGateway
from agent_platform.domain.model import (
    MessageRole,
    ModelRequest,
    ModelResult,
    ModelToolCall,
    TokenUsage,
)
from agent_platform.domain.observability import ObservationEvent


class FakeModel:
    provider = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.last_request: ModelRequest | None = None

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        self.last_request = request

        return ModelResult(
            provider="fake",
            model="fake-provider-model",
            output="gateway bridge works",
            provider_request_id="req-123",
            finish_reason="stop",
            usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=3,
                total_tokens=13,
            ),
        )


class NullObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        pass


def test_openai_compat_routes_through_model_contract(
    monkeypatch,
) -> None:
    fake_model = FakeModel()

    monkeypatch.setenv(
        "MODEL_GATEWAY_API_KEY",
        "internal-test-token",
    )

    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway(
        fake_model,
        NullObserver(),
    )

    session_id = "a68eafb6-52fc-4d8b-9123-705a375a43c3"

    try:
        client = TestClient(app)

        response = client.post(
            "/internal/v1/chat/completions",
            headers={
                "Authorization": "Bearer internal-test-token",
                "x-deepseek-harness-session-id": session_id,
            },
            json={
                "model": "logical-agent-model",
                "stream": True,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a test agent.",
                    },
                    {
                        "role": "user",
                        "content": "hello gateway",
                    },
                ],
                "tools": [
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
                ],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = [
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]

    assert events[-1] == "[DONE]"

    content = json.loads(events[0])
    finish = json.loads(events[1])

    assert content["choices"][0]["delta"]["content"] == ("gateway bridge works")
    assert finish["choices"][0]["finish_reason"] == "stop"
    assert finish["usage"]["total_tokens"] == 13

    assert fake_model.last_request is not None
    assert fake_model.last_request.run_id == UUID(session_id)
    assert len(fake_model.last_request.messages) == 2
    assert len(fake_model.last_request.tools) == 1

    tool = fake_model.last_request.tools[0]

    assert tool.name == "diagnostic_echo"
    assert tool.description == ("Echo a diagnostic message.")

    assert tool.input_schema["required"] == ["message"]


def test_openai_compat_maps_tool_history() -> None:
    messages = map_messages(
        [
            OpenAICompatMessage(
                role="assistant",
                tool_calls=[
                    {
                        "id": "call-123",
                        "type": "function",
                        "function": {
                            "name": "diagnostic_echo",
                            "arguments": ('{"message":"hello"}'),
                        },
                    }
                ],
            ),
            OpenAICompatMessage(
                role="tool",
                tool_call_id="call-123",
                content='{"message":"hello"}',
            ),
        ]
    )

    assert len(messages) == 2

    assistant = messages[0]

    assert assistant.role == MessageRole.ASSISTANT
    assert len(assistant.tool_calls) == 1
    assert assistant.tool_calls[0].name == "diagnostic_echo"

    tool = messages[1]

    assert tool.role == MessageRole.TOOL
    assert tool.tool_call_id == "call-123"


def test_openai_compat_streams_tool_calls() -> None:
    result = ModelResult(
        provider="fake",
        model="provider/tool-model",
        output="",
        tool_calls=[
            ModelToolCall(
                id="call-123",
                name="diagnostic_echo",
                arguments=('{"message":"agentic tool path works"}'),
            )
        ],
        provider_request_id="generation-123",
        finish_reason="tool_calls",
        usage=TokenUsage(
            prompt_tokens=10,
            completion_tokens=4,
            total_tokens=14,
        ),
    )

    events = list(stream_result(result))

    assert events[-1] == "data: [DONE]\n\n"

    first = json.loads(events[0].removeprefix("data: ").strip())

    finish = json.loads(events[1].removeprefix("data: ").strip())

    delta = first["choices"][0]["delta"]

    assert delta["role"] == "assistant"
    assert "content" not in delta

    assert delta["tool_calls"] == [
        {
            "index": 0,
            "id": "call-123",
            "type": "function",
            "function": {
                "name": "diagnostic_echo",
                "arguments": ('{"message":"agentic tool path works"}'),
            },
        }
    ]

    assert finish["choices"][0]["finish_reason"] == "tool_calls"
    assert finish["usage"]["total_tokens"] == 14
