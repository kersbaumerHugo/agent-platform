from __future__ import annotations

import httpx


class ModelGatewayPreflightError(RuntimeError):
    pass


class ModelGatewayPreflight:
    """Verify that the internal Model Gateway can serve a minimal request."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must not be empty.")

        if not api_key.strip():
            raise ValueError("api_key must not be empty.")

        if not model.strip():
            raise ValueError("model must not be empty.")

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def check(self) -> None:
        owns_client = self._client is None

        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)

        try:
            try:
                response = await client.post(
                    self._url,
                    headers={"Authorization": (f"Bearer {self._api_key}")},
                    json={
                        "model": self._model,
                        "stream": True,
                        "messages": [
                            {
                                "role": "user",
                                "content": ("Reply with exactly READY."),
                            }
                        ],
                        "temperature": 0,
                        "max_tokens": 8,
                    },
                )
            except httpx.HTTPError as exc:
                raise ModelGatewayPreflightError("Model Gateway preflight request failed.") from exc

            if response.status_code != 200:
                detail = self._safe_error_detail(response)

                raise ModelGatewayPreflightError(
                    f"Model Gateway preflight failed with HTTP {response.status_code}{detail}."
                )

            if "data: [DONE]" not in response.text:
                raise ModelGatewayPreflightError("Model Gateway preflight returned incomplete SSE.")
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _safe_error_detail(
        response: httpx.Response,
    ) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""

        if not isinstance(payload, dict):
            return ""

        detail = payload.get("detail")

        if not isinstance(detail, dict):
            return ""

        error_type = detail.get("type")

        if not isinstance(error_type, str):
            return ""

        return f" ({error_type})"
