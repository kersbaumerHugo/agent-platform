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


class _FunctionCall(BaseModel):
    name: str
    arguments: str


class _ToolCall(BaseModel):
    id: str
    type: str = "function"
    function: _FunctionCall


class _Message(BaseModel):
    content: str | None = None
    tool_calls: list[_ToolCall] = Field(default_factory=list)
    reasoning_content: str | None = None


class _Choice(BaseModel):
    message: _Message
    finish_reason: str | None = None


class _Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class _Response(BaseModel):
    id: str | None = None
    model: str
    choices: list[_Choice]
    usage: _Usage | None = None


class LocalOpenAIError(RuntimeError):
    pass


def _serialize_tool(tool: ModelToolDefinition) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _serialize_message(message: ModelMessage) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": message.role.value,
    }

    if message.content is not None:
        payload["content"] = message.content

    if message.role == MessageRole.ASSISTANT and message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": call.arguments,
                },
            }
            for call in message.tool_calls
        ]

    if message.role == MessageRole.ASSISTANT and message.reasoning_content is not None:
        payload["reasoning_content"] = message.reasoning_content

    if message.role == MessageRole.TOOL and message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id

    return payload


class LocalOpenAIModelAdapter(ModelContract):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 90.0,
        enable_thinking: bool = False,
        tracer: Tracer | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Local model API key must not be empty.")

        if not model:
            raise ValueError("Local model name must not be empty.")

        if not base_url:
            raise ValueError("Local model base URL must not be empty.")

        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._enable_thinking = enable_thinking
        self._tracer = tracer or trace.get_tracer("agent_platform.providers.local_openai")

    @property
    def provider(self) -> str:
        return "local"

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, request: ModelRequest) -> ModelResult:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [_serialize_message(message) for message in request.messages],
            "chat_template_kwargs": {
                "enable_thinking": self._enable_thinking,
            },
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
            with self._tracer.start_as_current_span("provider.local_openai") as span:
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

                try:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )

                    span.set_attribute(
                        "http.response.status_code",
                        response.status_code,
                    )

                    response.raise_for_status()

                    try:
                        response_payload = response.json()
                    except ValueError as exc:
                        raise LocalOpenAIError("Local model returned invalid JSON.") from exc

                    parsed = _Response.model_validate(response_payload)

                    if not parsed.choices:
                        raise LocalOpenAIError("Local model returned no choices.")

                    choice = parsed.choices[0]

                    tool_calls = [
                        ModelToolCall(
                            id=call.id,
                            name=call.function.name,
                            arguments=call.function.arguments,
                        )
                        for call in choice.message.tool_calls
                    ]

                    if choice.message.content is None and not tool_calls:
                        raise LocalOpenAIError("Local model returned neither text nor tool calls.")

                    usage = None

                    if parsed.usage is not None:
                        usage = TokenUsage(
                            prompt_tokens=parsed.usage.prompt_tokens,
                            completion_tokens=(parsed.usage.completion_tokens),
                            total_tokens=parsed.usage.total_tokens,
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

                    span.set_status(Status(StatusCode.OK))

                    return ModelResult(
                        provider=self.provider,
                        model=parsed.model,
                        output=choice.message.content or "",
                        tool_calls=tool_calls,
                        reasoning_content=(choice.message.reasoning_content),
                        provider_request_id=parsed.id,
                        finish_reason=choice.finish_reason,
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
