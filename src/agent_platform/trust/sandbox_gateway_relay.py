from __future__ import annotations

import asyncio
import os
from pathlib import Path


class GatewayRelayError(RuntimeError):
    pass


class UnixSocketGatewayCredentialRelay:
    """Expose one authenticated Model Gateway path through a Unix socket."""

    def __init__(
        self,
        *,
        socket_path: Path,
        upstream_host: str,
        upstream_port: int,
        gateway_api_key: str,
        request_path: str = "/internal/v1/chat/completions",
        max_header_bytes: int = 64 * 1024,
        max_body_bytes: int = 8 * 1024 * 1024,
        connect_timeout_seconds: float = 5.0,
        socket_mode: int = 0o660,
    ) -> None:
        if not upstream_host.strip():
            raise ValueError("upstream_host must not be empty.")

        if not 1 <= upstream_port <= 65535:
            raise ValueError("upstream_port must be between 1 and 65535.")

        if not gateway_api_key:
            raise ValueError("gateway_api_key must not be empty.")

        if not request_path.startswith("/"):
            raise ValueError("request_path must be an absolute path.")

        if max_header_bytes <= 0:
            raise ValueError("max_header_bytes must be greater than zero.")

        if max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be greater than zero.")

        if connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be greater than zero.")

        if not 0 <= socket_mode <= 0o777:
            raise ValueError("socket_mode must be a valid permission mode.")

        self._socket_path = socket_path
        self._upstream_host = upstream_host
        self._upstream_port = upstream_port
        self._gateway_api_key = gateway_api_key
        self._request_path = request_path
        self._max_header_bytes = max_header_bytes
        self._max_body_bytes = max_body_bytes
        self._connect_timeout_seconds = connect_timeout_seconds
        self._socket_mode = socket_mode
        self._server: asyncio.Server | None = None

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    async def start(self) -> Path:
        if self._server is not None:
            raise GatewayRelayError("Gateway relay is already started.")

        if self._socket_path.exists():
            raise GatewayRelayError("Gateway relay socket path already exists.")

        self._socket_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=self._socket_path,
            limit=self._max_header_bytes + 1,
        )

        os.chmod(
            self._socket_path,
            self._socket_mode,
        )

        return self._socket_path

    async def close(self) -> None:
        server = self._server
        self._server = None

        if server is not None:
            server.close()
            await server.wait_closed()

        try:
            self._socket_path.unlink()
        except FileNotFoundError:
            pass

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            await self._proxy_request(
                reader,
                writer,
            )
        except (
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            ConnectionError,
            OSError,
            TimeoutError,
            ValueError,
        ):
            await self._write_error(
                writer,
                status=400,
                reason="Bad Request",
            )
        finally:
            writer.close()

            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def _proxy_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        raw_headers = await reader.readuntil(b"\r\n\r\n")

        if len(raw_headers) > self._max_header_bytes:
            await self._write_error(
                writer,
                status=431,
                reason="Request Header Fields Too Large",
            )
            return

        request_line, headers = self._parse_headers(raw_headers)

        method, target, version = request_line.split(
            " ",
            2,
        )
        path = target.partition("?")[0]

        if method != "POST" or path != self._request_path:
            await self._write_error(
                writer,
                status=403,
                reason="Forbidden",
            )
            return

        if version not in {
            "HTTP/1.0",
            "HTTP/1.1",
        }:
            await self._write_error(
                writer,
                status=400,
                reason="Bad Request",
            )
            return

        transfer_encoding = self._header_value(
            headers,
            "transfer-encoding",
        )

        if transfer_encoding is not None:
            await self._write_error(
                writer,
                status=400,
                reason="Bad Request",
            )
            return

        content_length_text = self._header_value(
            headers,
            "content-length",
        )

        if content_length_text is None:
            await self._write_error(
                writer,
                status=411,
                reason="Length Required",
            )
            return

        content_length = int(content_length_text)

        if content_length < 0 or content_length > self._max_body_bytes:
            await self._write_error(
                writer,
                status=413,
                reason="Content Too Large",
            )
            return

        body = await reader.readexactly(content_length)

        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(
                    self._upstream_host,
                    self._upstream_port,
                ),
                timeout=self._connect_timeout_seconds,
            )
        except (OSError, TimeoutError):
            await self._write_error(
                writer,
                status=502,
                reason="Bad Gateway",
            )
            return

        try:
            upstream_writer.write(
                self._build_upstream_headers(
                    request_line=request_line,
                    headers=headers,
                    content_length=content_length,
                )
            )
            upstream_writer.write(body)
            await upstream_writer.drain()

            while True:
                chunk = await upstream_reader.read(64 * 1024)

                if not chunk:
                    break

                writer.write(chunk)
                await writer.drain()
        finally:
            upstream_writer.close()

            try:
                await upstream_writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    @staticmethod
    def _parse_headers(
        raw_headers: bytes,
    ) -> tuple[str, tuple[tuple[str, str], ...]]:
        decoded = raw_headers.decode("iso-8859-1")
        lines = decoded.split("\r\n")

        request_line = lines[0].strip()

        if not request_line:
            raise ValueError("Missing request line.")

        headers: list[tuple[str, str]] = []

        for line in lines[1:]:
            if not line:
                continue

            name, separator, value = line.partition(":")

            if not separator or not name.strip():
                raise ValueError("Malformed request header.")

            headers.append(
                (
                    name.strip(),
                    value.strip(),
                )
            )

        return request_line, tuple(headers)

    @staticmethod
    def _header_value(
        headers: tuple[tuple[str, str], ...],
        name: str,
    ) -> str | None:
        expected = name.lower()

        for header_name, value in headers:
            if header_name.lower() == expected:
                return value

        return None

    def _build_upstream_headers(
        self,
        *,
        request_line: str,
        headers: tuple[tuple[str, str], ...],
        content_length: int,
    ) -> bytes:
        filtered = [
            (name, value)
            for name, value in headers
            if name.lower()
            not in {
                "authorization",
                "proxy-authorization",
                "connection",
                "host",
                "content-length",
            }
        ]

        host = self._upstream_host

        if self._upstream_port != 80:
            host = f"{host}:{self._upstream_port}"

        lines = [
            request_line,
            f"Host: {host}",
            (f"Authorization: Bearer {self._gateway_api_key}"),
            "Connection: close",
            (f"Content-Length: {content_length}"),
            *[f"{name}: {value}" for name, value in filtered],
            "",
            "",
        ]

        return "\r\n".join(lines).encode("iso-8859-1")

    @staticmethod
    async def _write_error(
        writer: asyncio.StreamWriter,
        *,
        status: int,
        reason: str,
    ) -> None:
        if writer.is_closing():
            return

        response = (
            f"HTTP/1.1 {status} {reason}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        ).encode("ascii")

        writer.write(response)

        try:
            await writer.drain()
        except (ConnectionError, OSError):
            pass
