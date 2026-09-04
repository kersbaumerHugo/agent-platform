import httpx
from pydantic import BaseModel

from agent_platform.contracts.model import ModelContract
from agent_platform.domain.model import ModelRequest, ModelResult, TokenUsage


class _OpenRouterMessage(BaseModel):
    content: str | None = None


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


class OpenRouterModelAdapter(ModelContract):
    def __init__(
        self,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 30.0,
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

    @property
    def provider(self) -> str:
        return "openrouter"

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, request: ModelRequest) -> ModelResult:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [message.model_dump(mode="json") for message in request.messages],
        }

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
            response = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            parsed = _OpenRouterResponse.model_validate(response.json())
        finally:
            if owns_client:
                await client.aclose()

        if not parsed.choices:
            raise RuntimeError("OpenRouter returned no choices.")

        choice = parsed.choices[0]

        if choice.message.content is None:
            raise RuntimeError("OpenRouter returned no text content.")

        usage = None
        if parsed.usage is not None:
            usage = TokenUsage(
                prompt_tokens=parsed.usage.prompt_tokens,
                completion_tokens=parsed.usage.completion_tokens,
                total_tokens=parsed.usage.total_tokens,
            )

        return ModelResult(
            provider=self.provider,
            model=parsed.model,
            output=choice.message.content,
            provider_request_id=parsed.id,
            finish_reason=choice.finish_reason,
            usage=usage,
        )
