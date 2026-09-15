import httpx
import pytest

from agent_platform.worker.model_gateway_preflight import (
    ModelGatewayPreflight,
    ModelGatewayPreflightError,
)


@pytest.mark.asyncio
async def test_preflight_accepts_completed_sse() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer internal-key"

        return httpx.Response(
            200,
            text=('data: {"choices": []}\n\ndata: [DONE]\n\n'),
            headers={"content-type": ("text/event-stream")},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        probe = ModelGatewayPreflight(
            base_url=("http://gateway/internal/v1"),
            api_key="internal-key",
            model="test-model",
            client=client,
        )

        await probe.check()


@pytest.mark.asyncio
async def test_preflight_rejects_upstream_failure() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            502,
            json={
                "detail": {
                    "type": ("upstream_provider_error"),
                    "message": ("Service temporarily overloaded"),
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        probe = ModelGatewayPreflight(
            base_url=("http://gateway/internal/v1"),
            api_key="internal-key",
            model="test-model",
            client=client,
        )

        with pytest.raises(
            ModelGatewayPreflightError,
            match=(
                "HTTP 502 "
                r"\(upstream_provider_error\)"
            ),
        ):
            await probe.check()


@pytest.mark.asyncio
async def test_preflight_rejects_incomplete_sse() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            text='data: {"choices": []}\n\n',
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        probe = ModelGatewayPreflight(
            base_url=("http://gateway/internal/v1"),
            api_key="internal-key",
            model="test-model",
            client=client,
        )

        with pytest.raises(
            ModelGatewayPreflightError,
            match="incomplete SSE",
        ):
            await probe.check()
