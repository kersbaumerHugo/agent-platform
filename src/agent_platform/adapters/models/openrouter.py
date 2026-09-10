import httpx
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, Tracer
from pydantic import BaseModel, Field

from agent_platform.contracts.model import ModelContract
from agent_platform.domain.model import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelResult,
    ModelToolCall,
    ModelToolDefinition,
    TokenUsage,
)


class _OpenRouterFunctionCall(BaseModel):
    name: str
    arguments: str


class _OpenRouterToolCall(BaseModel):
    id: str
    type: str = "function"
    function: _OpenRouterFunctionCall


class _OpenRouterMessage(BaseModel):
    content: str | None = None

    tool_calls: list[_OpenRouterToolCall] = Field(default_factory=list)

    reasoning_content: str | None = None


class _OpenRouterChoice(BaseModel):
    message: _OpenRouterMessage
    finish_reason: str | None = None


class _OpenRouterUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class _OpenRouterResponse(BaseModel):
    id: str | None = None
    model: str
    choices: list[_OpenRouterChoice]
    usage: _OpenRouterUsage | None = None


def _serialize_tool(
    tool: ModelToolDefinition,
) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _serialize_message(
    message: ModelMessage,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": message.role.value,
    }

    if message.content is not None:
        payload["content"] = message.content

    if message.role == MessageRole.ASSISTANT and message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                },
            }
            for tool_call in message.tool_calls
        ]

    if message.role == MessageRole.ASSISTANT and message.reasoning_content is not None:
        payload["reasoning_content"] = message.reasoning_content

    if message.role == MessageRole.TOOL and message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id

    return payload


class OpenRouterModelAdapter(ModelContract):
    def __init__(
        self,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 30.0,
        tracer: Tracer | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouter API key must not be empty.")

        if not model:
            raise ValueError("OpenRouter model must not be empty.")

        self._api_key = api_key
        self._model = model
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._tracer = tracer or trace.get_tracer("agent_platform.providers.openrouter")

    @property
    def provider(self) -> str:
        return "openrouter"

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [_serialize_message(message) for message in request.messages],
        }

        if request.tools:
            payload["tools"] = [_serialize_tool(tool) for tool in request.tools]

        if request.temperature is not None:
            payload["temperature"] = request.temperature

        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        owns_client = self._client is None

        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)

        try:
            with self._tracer.start_as_current_span("provider.openrouter") as span:
                span.set_attribute(
                    "agent_platform.run.id",
                    str(request.run_id),
                )
                span.set_attribute(
                    "gen_ai.provider.name",
                    self.provider,
                )
                span.set_attribute(
                    "gen_ai.request.model",
                    self.model,
                )

                if request.tools:
                    span.set_attribute(
                        "gen_ai.tool.count",
                        len(request.tools),
                    )

                try:
                    response = await client.post(
                        (f"{self._base_url}/chat/completions"),
                        json=payload,
                        headers=headers,
                    )

                    response.raise_for_status()

                    span.set_attribute(
                        "http.response.status_code",
                        response.status_code,
                    )

                    parsed = _OpenRouterResponse.model_validate(response.json())

                    if not parsed.choices:
                        raise RuntimeError("OpenRouter returned no choices.")

                    choice = parsed.choices[0]

                    tool_calls = [
                        ModelToolCall(
                            id=tool_call.id,
                            name=(tool_call.function.name),
                            arguments=(tool_call.function.arguments),
                        )
                        for tool_call in choice.message.tool_calls
                    ]

                    if choice.message.content is None and not tool_calls:
                        raise RuntimeError("OpenRouter returned neither text nor tool calls.")

                    usage = None

                    if parsed.usage is not None:
                        usage = TokenUsage(
                            prompt_tokens=(parsed.usage.prompt_tokens),
                            completion_tokens=(parsed.usage.completion_tokens),
                            total_tokens=(parsed.usage.total_tokens),
                        )

                        span.set_attribute(
                            "gen_ai.usage.input_tokens",
                            usage.prompt_tokens,
                        )
                        span.set_attribute(
                            "gen_ai.usage.output_tokens",
                            usage.completion_tokens,
                        )

                    span.set_attribute(
                        "gen_ai.response.model",
                        parsed.model,
                    )

                    if tool_calls:
                        span.set_attribute(
                            "gen_ai.tool.call_count",
                            len(tool_calls),
                        )

                    span.set_status(Status(StatusCode.OK))

                    return ModelResult(
                        provider=self.provider,
                        model=parsed.model,
                        output=(choice.message.content or ""),
                        tool_calls=tool_calls,
                        reasoning_content=(choice.message.reasoning_content),
                        provider_request_id=(parsed.id),
                        finish_reason=(choice.finish_reason),
                        usage=usage,
                    )

                except Exception as exc:
                    span.set_attribute(
                        "error.type",
                        type(exc).__name__,
                    )
                    span.record_exception(exc)
                    span.set_status(
                        Status(
                            StatusCode.ERROR,
                            type(exc).__name__,
                        )
                    )
                    raise

        finally:
            if owns_client:
                await client.aclose()
