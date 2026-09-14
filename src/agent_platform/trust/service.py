from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_platform.trust.change_request import (
    ChangeRequestError,
    deserialize_change_set,
)
from agent_platform.trust.publisher import (
    ChangeRejectedError,
    TrustedPublisher,
)

MAX_REQUEST_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ChangeServiceResponse:
    status: str
    reference: str | None = None
    reason_code: str | None = None
    blocked_paths: tuple[str, ...] = ()
    error_code: str | None = None

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "status": self.status,
        }

        if self.reference is not None:
            payload["reference"] = self.reference

        if self.reason_code is not None:
            payload["reason_code"] = self.reason_code

        if self.blocked_paths:
            payload["blocked_paths"] = list(self.blocked_paths)

        if self.error_code is not None:
            payload["error_code"] = self.error_code

        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )


class TrustedChangeHandler:
    def __init__(
        self,
        publisher: TrustedPublisher,
    ) -> None:
        self._publisher = publisher

    async def handle(
        self,
        raw_request: str,
    ) -> ChangeServiceResponse:
        try:
            change_set = deserialize_change_set(raw_request)
        except ChangeRequestError:
            return ChangeServiceResponse(
                status="error",
                error_code="invalid_change_request",
            )

        try:
            result = await self._publisher.publish(change_set)
        except ChangeRejectedError as exc:
            return ChangeServiceResponse(
                status="rejected",
                reason_code=exc.decision.reason_code,
                blocked_paths=(exc.decision.blocked_paths),
            )
        except Exception:
            return ChangeServiceResponse(
                status="error",
                error_code="publication_failed",
            )

        return ChangeServiceResponse(
            status="accepted",
            reference=result.reference,
        )


class UnixSocketChangeServer:
    def __init__(
        self,
        socket_path: Path,
        handler: TrustedChangeHandler,
    ) -> None:
        self._socket_path = socket_path
        self._handler = handler
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("Server is already started.")

        if self._socket_path.exists():
            raise RuntimeError("Socket path already exists.")

        self._socket_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=self._socket_path,
            limit=MAX_REQUEST_BYTES + 1,
        )

    async def close(self) -> None:
        if self._server is None:
            return

        self._server.close()
        await self._server.wait_closed()
        self._server = None

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
            raw = await reader.readline()

            if not raw or len(raw) > MAX_REQUEST_BYTES or not raw.endswith(b"\n"):
                response = ChangeServiceResponse(
                    status="error",
                    error_code="invalid_transport_request",
                )
            else:
                try:
                    decoded = raw[:-1].decode("utf-8")
                except UnicodeDecodeError:
                    response = ChangeServiceResponse(
                        status="error",
                        error_code="invalid_encoding",
                    )
                else:
                    response = await self._handler.handle(decoded)

            writer.write(response.to_json().encode("utf-8") + b"\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
