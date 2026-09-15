from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from agent_platform.trust.change_request import (
    serialize_change_set,
)
from agent_platform.trust.publisher import ChangeSet


class TrustedPublicationClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrustedPublicationResponse:
    status: str
    reference: str | None = None
    reason_code: str | None = None
    blocked_paths: tuple[str, ...] = ()
    error_code: str | None = None


class TrustedPublicationClient:
    """Submit an untrusted ChangeSet to the trusted publication boundary."""

    def __init__(
        self,
        *,
        socket_path: Path,
    ) -> None:
        self._socket_path = socket_path

    async def publish(
        self,
        change_set: ChangeSet,
    ) -> TrustedPublicationResponse:
        try:
            reader, writer = await asyncio.open_unix_connection(self._socket_path)
        except OSError as exc:
            raise TrustedPublicationClientError("Unable to connect to trusted publisher.") from exc

        try:
            payload = serialize_change_set(change_set).encode("utf-8") + b"\n"

            writer.write(payload)
            await writer.drain()

            raw_response = await reader.readline()

            if not raw_response:
                raise TrustedPublicationClientError("Trusted publisher returned no response.")

            try:
                response = json.loads(raw_response)
            except json.JSONDecodeError as exc:
                raise TrustedPublicationClientError(
                    "Trusted publisher returned invalid JSON."
                ) from exc

            if not isinstance(response, dict):
                raise TrustedPublicationClientError("Trusted publisher returned invalid response.")

            return TrustedPublicationResponse(
                status=str(response.get("status", "")),
                reference=response.get("reference"),
                reason_code=response.get("reason_code"),
                blocked_paths=tuple(response.get("blocked_paths", ())),
                error_code=response.get("error_code"),
            )
        finally:
            writer.close()
            await writer.wait_closed()
