from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

MAX_DIAGNOSTIC_REQUEST_BYTES = 1024
MAX_DIAGNOSTIC_RESPONSE_BYTES = 64 * 1024
MAX_DIAGNOSTIC_OUTPUT_CHARS = 8192

_DIAGNOSTIC_OPERATION = "full_pytest"


class DiagnosticVerificationStatus(StrEnum):
    ACCEPTED = "accepted"
    ERROR = "error"


@dataclass(frozen=True)
class DiagnosticVerificationRequest:
    operation: str = _DIAGNOSTIC_OPERATION

    def __post_init__(self) -> None:
        if self.operation != _DIAGNOSTIC_OPERATION:
            raise ValueError("Unsupported diagnostic verification operation.")


@dataclass(frozen=True)
class DiagnosticVerificationResult:
    exit_code: int | None
    output: str
    timed_out: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.exit_code, bool):
            raise ValueError("exit_code must be an integer or null.")

        if self.exit_code is not None and not isinstance(
            self.exit_code,
            int,
        ):
            raise ValueError("exit_code must be an integer or null.")

        if self.timed_out:
            if self.exit_code is not None:
                raise ValueError("Timed-out diagnostic verification must not have an exit code.")
        elif self.exit_code is None:
            raise ValueError("Completed diagnostic verification requires an exit code.")

        if len(self.output) > MAX_DIAGNOSTIC_OUTPUT_CHARS:
            raise ValueError("Diagnostic verification output exceeds limit.")


@dataclass(frozen=True)
class DiagnosticVerificationResponse:
    status: DiagnosticVerificationStatus
    result: DiagnosticVerificationResult | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.status is DiagnosticVerificationStatus.ACCEPTED:
            if self.result is None:
                raise ValueError("Accepted diagnostic response requires result.")

            if self.error_code is not None:
                raise ValueError("Accepted diagnostic response must not include error_code.")

            return

        if self.result is not None:
            raise ValueError("Error diagnostic response must not include result.")

        if self.error_code is None or not self.error_code.strip():
            raise ValueError("Error diagnostic response requires error_code.")


class DiagnosticVerificationAuthority(Protocol):
    async def verify(self) -> DiagnosticVerificationResult: ...


class TrustedDiagnosticVerificationClientError(RuntimeError):
    pass


def serialize_diagnostic_request(
    request: DiagnosticVerificationRequest,
) -> str:
    return json.dumps(
        {
            "version": 1,
            "operation": request.operation,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def deserialize_diagnostic_request(
    raw: str,
) -> DiagnosticVerificationRequest:
    payload = _object(raw)

    if set(payload) != {
        "version",
        "operation",
    }:
        raise ValueError("Diagnostic request contains missing or unexpected fields.")

    if payload["version"] != 1:
        raise ValueError("Unsupported diagnostic request version.")

    operation = payload["operation"]

    if not isinstance(operation, str):
        raise ValueError("Diagnostic operation must be a string.")

    return DiagnosticVerificationRequest(
        operation=operation,
    )


def serialize_diagnostic_response(
    response: DiagnosticVerificationResponse,
) -> str:
    result = None

    if response.result is not None:
        result = {
            "exit_code": response.result.exit_code,
            "output": response.result.output,
            "timed_out": response.result.timed_out,
        }

    return json.dumps(
        {
            "version": 1,
            "status": response.status.value,
            "result": result,
            "error_code": response.error_code,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def deserialize_diagnostic_response(
    raw: str,
) -> DiagnosticVerificationResponse:
    payload = _object(raw)

    if set(payload) != {
        "version",
        "status",
        "result",
        "error_code",
    }:
        raise ValueError("Diagnostic response contains missing or unexpected fields.")

    if payload["version"] != 1:
        raise ValueError("Unsupported diagnostic response version.")

    status_raw = payload["status"]

    if not isinstance(status_raw, str):
        raise ValueError("status must be a string.")

    status = DiagnosticVerificationStatus(status_raw)

    error_code = payload["error_code"]

    if error_code is not None and not isinstance(
        error_code,
        str,
    ):
        raise ValueError("error_code must be a string or null.")

    result_raw = payload["result"]
    result = None

    if result_raw is not None:
        if not isinstance(result_raw, dict):
            raise ValueError("Diagnostic result must be an object.")

        if set(result_raw) != {
            "exit_code",
            "output",
            "timed_out",
        }:
            raise ValueError("Diagnostic result contains invalid fields.")

        exit_code = result_raw["exit_code"]
        output = result_raw["output"]
        timed_out = result_raw["timed_out"]

        if not isinstance(output, str):
            raise ValueError("output must be a string.")

        if not isinstance(timed_out, bool):
            raise ValueError("timed_out must be a boolean.")

        result = DiagnosticVerificationResult(
            exit_code=exit_code,
            output=output,
            timed_out=timed_out,
        )

    return DiagnosticVerificationResponse(
        status=status,
        result=result,
        error_code=error_code,
    )


class TrustedDiagnosticVerificationHandler:
    def __init__(
        self,
        *,
        authority: DiagnosticVerificationAuthority,
        max_requests: int = 2,
    ) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be greater than zero.")

        self._authority = authority
        self._max_requests = max_requests
        self._requests_consumed = 0
        self._lock = asyncio.Lock()

    @property
    def requests_consumed(self) -> int:
        return self._requests_consumed

    async def handle(
        self,
        raw_request: str,
    ) -> DiagnosticVerificationResponse:
        try:
            deserialize_diagnostic_request(raw_request)
        except (ValueError, json.JSONDecodeError):
            return self._error("invalid_diagnostic_request")

        async with self._lock:
            if self._requests_consumed >= self._max_requests:
                return self._error("diagnostic_request_budget_exhausted")

            self._requests_consumed += 1

            try:
                result = await self._authority.verify()
            except Exception:
                return self._error("diagnostic_verification_failed")

        return DiagnosticVerificationResponse(
            status=DiagnosticVerificationStatus.ACCEPTED,
            result=result,
        )

    @staticmethod
    def _error(
        error_code: str,
    ) -> DiagnosticVerificationResponse:
        return DiagnosticVerificationResponse(
            status=DiagnosticVerificationStatus.ERROR,
            error_code=error_code,
        )


class UnixSocketDiagnosticVerificationServer:
    def __init__(
        self,
        *,
        socket_path: Path,
        handler: TrustedDiagnosticVerificationHandler,
    ) -> None:
        self._socket_path = socket_path
        self._handler = handler
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("Diagnostic verification server is already started.")

        if self._socket_path.exists():
            raise RuntimeError("Diagnostic verification socket path already exists.")

        self._socket_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=self._socket_path,
            limit=MAX_DIAGNOSTIC_REQUEST_BYTES + 1,
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
            try:
                raw = await reader.readline()
            except (
                asyncio.LimitOverrunError,
                ValueError,
            ):
                response = TrustedDiagnosticVerificationHandler._error("invalid_transport_request")
            else:
                if not raw or len(raw) > MAX_DIAGNOSTIC_REQUEST_BYTES or not raw.endswith(b"\n"):
                    response = TrustedDiagnosticVerificationHandler._error(
                        "invalid_transport_request"
                    )
                else:
                    try:
                        decoded = raw[:-1].decode("utf-8")
                    except UnicodeDecodeError:
                        response = TrustedDiagnosticVerificationHandler._error("invalid_encoding")
                    else:
                        response = await self._handler.handle(decoded)

            encoded = serialize_diagnostic_response(response).encode("utf-8") + b"\n"

            writer.write(encoded)
            await writer.drain()
        finally:
            writer.close()

            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass


class TrustedDiagnosticVerificationClient:
    def __init__(
        self,
        *,
        socket_path: Path,
    ) -> None:
        self._socket_path = socket_path

    async def verify(
        self,
    ) -> DiagnosticVerificationResult:
        try:
            reader, writer = await asyncio.open_unix_connection(
                self._socket_path,
                limit=(MAX_DIAGNOSTIC_RESPONSE_BYTES + 1),
            )
        except OSError as exc:
            raise TrustedDiagnosticVerificationClientError(
                "Unable to connect to diagnostic verifier."
            ) from exc

        try:
            request = DiagnosticVerificationRequest()

            writer.write(serialize_diagnostic_request(request).encode("utf-8") + b"\n")
            await writer.drain()

            try:
                raw = await reader.readline()
            except (
                asyncio.LimitOverrunError,
                ValueError,
            ) as exc:
                raise (
                    TrustedDiagnosticVerificationClientError(
                        "Diagnostic verifier response exceeded protocol limit."
                    )
                ) from exc

            if not raw or len(raw) > MAX_DIAGNOSTIC_RESPONSE_BYTES or not raw.endswith(b"\n"):
                raise TrustedDiagnosticVerificationClientError(
                    "Diagnostic verifier returned an invalid response."
                )

            try:
                response = deserialize_diagnostic_response(raw[:-1].decode("utf-8"))
            except (
                UnicodeDecodeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                raise (
                    TrustedDiagnosticVerificationClientError(
                        "Diagnostic verifier returned an invalid response."
                    )
                ) from exc

            if response.status is DiagnosticVerificationStatus.ERROR:
                raise TrustedDiagnosticVerificationClientError(
                    f"Diagnostic verifier failed: {response.error_code}"
                )

            if response.result is None:
                raise TrustedDiagnosticVerificationClientError(
                    "Diagnostic verifier returned no result."
                )

            return response.result
        finally:
            writer.close()

            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass


def _object(
    raw: str,
) -> dict[str, Any]:
    payload = json.loads(raw)

    if not isinstance(payload, dict):
        raise ValueError("Protocol payload must be an object.")

    return payload
