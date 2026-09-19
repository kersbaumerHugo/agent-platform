from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from agent_platform.trust.sandbox_gateway_relay import (
    GatewayRelayError,
    UnixSocketGatewayCredentialRelay,
)


@dataclass
class CapturedRequest:
    request_line: str
    headers: dict[str, str]
    body: bytes


async def read_http_response(
    reader: asyncio.StreamReader,
) -> bytes:
    chunks: list[bytes] = []

    while True:
        chunk = await reader.read(4096)

        if not chunk:
            break

        chunks.append(chunk)

    return b"".join(chunks)


async def build_upstream(
    captured: list[CapturedRequest],
) -> asyncio.Server:
    async def handler(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        raw = await reader.readuntil(b"\r\n\r\n")
        decoded = raw.decode("iso-8859-1")
        lines = decoded.split("\r\n")
        request_line = lines[0]
        headers = {
            name.strip().lower(): value.strip()
            for line in lines[1:]
            if line
            for name, separator, value in [line.partition(":")]
            if separator
        }

        content_length = int(headers["content-length"])
        body = await reader.readexactly(content_length)

        captured.append(
            CapturedRequest(
                request_line=request_line,
                headers=headers,
                body=body,
            )
        )

        payload = b'{"detail":"streaming required"}'

        writer.write(
            b"HTTP/1.1 400 Bad Request\r\n"
            + (f"Content-Length: {len(payload)}\r\n").encode()
            + (b"Content-Type: application/json\r\n")
            + b"Connection: close\r\n\r\n"
            + payload
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    return await asyncio.start_server(
        handler,
        "127.0.0.1",
        0,
    )


def upstream_port(
    server: asyncio.Server,
) -> int:
    sockets = server.sockets
    assert sockets

    port = sockets[0].getsockname()[1]
    assert isinstance(port, int)

    return port


@pytest.mark.asyncio
async def test_unix_relay_injects_real_gateway_credential(
    tmp_path: Path,
) -> None:
    captured: list[CapturedRequest] = []
    upstream = await build_upstream(captured)

    socket_path = tmp_path / "gateway.sock"

    relay = UnixSocketGatewayCredentialRelay(
        socket_path=socket_path,
        upstream_host="127.0.0.1",
        upstream_port=upstream_port(upstream),
        gateway_api_key=("real-gateway-secret"),
    )

    await relay.start()

    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)

        body = b'{"stream":false}'

        writer.write(
            (
                "POST "
                "/internal/v1/chat/completions "
                "HTTP/1.1\r\n"
                "Host: sandbox-relay\r\n"
                "Authorization: Bearer "
                "fake-container-token\r\n"
                "Content-Type: "
                "application/json\r\n"
                f"Content-Length: "
                f"{len(body)}\r\n"
                "X-DeepSeek-Harness-Session-Id: "
                "run-123\r\n"
                "\r\n"
            ).encode()
            + body
        )
        await writer.drain()

        response = await read_http_response(reader)

        writer.close()
        await writer.wait_closed()
    finally:
        await relay.close()
        upstream.close()
        await upstream.wait_closed()

    assert response.startswith(b"HTTP/1.1 400 Bad Request")
    assert len(captured) == 1

    request = captured[0]

    assert request.headers["authorization"] == "Bearer real-gateway-secret"
    assert request.headers["x-deepseek-harness-session-id"] == "run-123"
    assert "fake-container-token" not in "\n".join(
        f"{name}:{value}" for name, value in request.headers.items()
    )
    assert request.body == body


@pytest.mark.asyncio
async def test_unix_relay_rejects_non_gateway_path(
    tmp_path: Path,
) -> None:
    upstream_called = asyncio.Event()

    async def handler(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        del reader
        upstream_called.set()
        writer.close()
        await writer.wait_closed()

    upstream = await asyncio.start_server(
        handler,
        "127.0.0.1",
        0,
    )

    socket_path = tmp_path / "gateway.sock"
    relay = UnixSocketGatewayCredentialRelay(
        socket_path=socket_path,
        upstream_host="127.0.0.1",
        upstream_port=upstream_port(upstream),
        gateway_api_key=("real-gateway-secret"),
    )

    await relay.start()

    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)

        writer.write(b"POST /health HTTP/1.1\r\nHost: gateway\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()

        response = await read_http_response(reader)

        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0)
    finally:
        await relay.close()
        upstream.close()
        await upstream.wait_closed()

    assert response.startswith(b"HTTP/1.1 403 Forbidden")
    assert not upstream_called.is_set()


@pytest.mark.asyncio
async def test_unix_relay_removes_socket_on_close(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "gateway.sock"

    relay = UnixSocketGatewayCredentialRelay(
        socket_path=socket_path,
        upstream_host="127.0.0.1",
        upstream_port=8000,
        gateway_api_key=("real-gateway-secret"),
    )

    await relay.start()

    assert socket_path.is_socket()
    assert (socket_path.stat().st_mode & 0o777) == 0o660

    await relay.close()
    await relay.close()

    assert not socket_path.exists()


@pytest.mark.asyncio
async def test_unix_relay_rejects_existing_socket_path(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "gateway.sock"
    socket_path.write_text(
        "do not replace",
        encoding="utf-8",
    )

    relay = UnixSocketGatewayCredentialRelay(
        socket_path=socket_path,
        upstream_host="127.0.0.1",
        upstream_port=8000,
        gateway_api_key=("real-gateway-secret"),
    )

    with pytest.raises(
        GatewayRelayError,
        match="already exists",
    ):
        await relay.start()

    assert socket_path.read_text(encoding="utf-8") == "do not replace"
