from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from agent_platform.trust.sandbox_execution import (
    TrustedWorkspaceError,
    TrustedWorkspaceResolver,
)
from agent_platform.trust.verification import (
    VerificationOutcome,
    VerificationResult,
    VerificationStepResult,
)
from agent_platform.trust.verification_profile import (
    VerificationCheck,
)

MAX_VERIFICATION_REQUEST_BYTES = 8 * 1024
MAX_VERIFICATION_RESPONSE_BYTES = 64 * 1024


class VerificationServiceStatus(StrEnum):
    ACCEPTED = "accepted"
    ERROR = "error"


@dataclass(frozen=True)
class VerificationServiceRequest:
    workspace_name: str

    def __post_init__(self) -> None:
        normalized = self.workspace_name.strip()

        if not normalized:
            raise ValueError("workspace_name must not be empty.")

        object.__setattr__(
            self,
            "workspace_name",
            normalized,
        )


@dataclass(frozen=True)
class VerificationServiceResponse:
    status: VerificationServiceStatus
    result: VerificationResult | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.status is VerificationServiceStatus.ACCEPTED:
            if self.result is None:
                raise ValueError("Accepted verification response requires result.")

            if self.error_code is not None:
                raise ValueError("Accepted verification response must not include error_code.")

            return

        if self.result is not None:
            raise ValueError("Error verification response must not include result.")

        if self.error_code is None or not self.error_code.strip():
            raise ValueError("Error verification response requires error_code.")


class VerificationAuthority(Protocol):
    async def verify(
        self,
        *,
        workspace: Path,
    ) -> VerificationResult: ...


class TrustedVerificationClientError(RuntimeError):
    pass


def serialize_verification_request(
    request: VerificationServiceRequest,
) -> str:
    return json.dumps(
        {
            "version": 1,
            "workspace_name": request.workspace_name,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def deserialize_verification_request(
    raw: str,
) -> VerificationServiceRequest:
    payload = _object(raw)

    if set(payload) != {
        "version",
        "workspace_name",
    }:
        raise ValueError("Verification request contains missing or unexpected fields.")

    if payload["version"] != 1:
        raise ValueError("Unsupported verification request version.")

    workspace_name = payload["workspace_name"]

    if not isinstance(workspace_name, str):
        raise ValueError("workspace_name must be a string.")

    return VerificationServiceRequest(
        workspace_name=workspace_name,
    )


def serialize_verification_response(
    response: VerificationServiceResponse,
) -> str:
    result = None

    if response.result is not None:
        result = {
            "profile_version": response.result.profile_version,
            "outcome": response.result.outcome.value,
            "reason_code": response.result.reason_code,
            "steps": [
                {
                    "check": step.check.value,
                    "outcome": step.outcome.value,
                    "exit_code": step.exit_code,
                    "summary": step.summary,
                }
                for step in response.result.steps
            ],
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


def deserialize_verification_response(
    raw: str,
) -> VerificationServiceResponse:
    payload = _object(raw)

    if set(payload) != {
        "version",
        "status",
        "result",
        "error_code",
    }:
        raise ValueError("Verification response contains missing or unexpected fields.")

    if payload["version"] != 1:
        raise ValueError("Unsupported verification response version.")

    status_raw = payload["status"]

    if not isinstance(status_raw, str):
        raise ValueError("status must be a string.")

    status = VerificationServiceStatus(status_raw)

    error_code = payload["error_code"]

    if error_code is not None and not isinstance(
        error_code,
        str,
    ):
        raise ValueError("error_code must be a string or null.")

    result_raw = payload["result"]

    result = None if result_raw is None else _verification_result(result_raw)

    return VerificationServiceResponse(
        status=status,
        result=result,
        error_code=error_code,
    )


class TrustedVerificationHandler:
    def __init__(
        self,
        *,
        workspace_resolver: TrustedWorkspaceResolver,
        verifier: VerificationAuthority,
    ) -> None:
        self._workspace_resolver = workspace_resolver
        self._verifier = verifier
        self._lock = asyncio.Lock()

    async def handle(
        self,
        raw_request: str,
    ) -> VerificationServiceResponse:
        try:
            request = deserialize_verification_request(raw_request)
        except (ValueError, json.JSONDecodeError):
            return self._error("invalid_verification_request")

        try:
            workspace = self._workspace_resolver.resolve(request.workspace_name)
        except TrustedWorkspaceError:
            return self._error("invalid_workspace")

        try:
            async with self._lock:
                result = await self._verifier.verify(
                    workspace=workspace,
                )
        except Exception:
            return self._error("verification_failed")

        return VerificationServiceResponse(
            status=VerificationServiceStatus.ACCEPTED,
            result=result,
        )

    @staticmethod
    def _error(
        error_code: str,
    ) -> VerificationServiceResponse:
        return VerificationServiceResponse(
            status=VerificationServiceStatus.ERROR,
            error_code=error_code,
        )


class UnixSocketVerificationServer:
    def __init__(
        self,
        *,
        socket_path: Path,
        handler: TrustedVerificationHandler,
    ) -> None:
        self._socket_path = socket_path
        self._handler = handler
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("Verification server is already started.")

        if self._socket_path.exists():
            raise RuntimeError("Verification socket path already exists.")

        self._socket_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=self._socket_path,
            limit=MAX_VERIFICATION_REQUEST_BYTES + 1,
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
                response = TrustedVerificationHandler._error("invalid_transport_request")
            else:
                if not raw or len(raw) > MAX_VERIFICATION_REQUEST_BYTES or not raw.endswith(b"\n"):
                    response = TrustedVerificationHandler._error("invalid_transport_request")
                else:
                    try:
                        decoded = raw[:-1].decode("utf-8")
                    except UnicodeDecodeError:
                        response = TrustedVerificationHandler._error("invalid_encoding")
                    else:
                        response = await self._handler.handle(decoded)

            encoded = serialize_verification_response(response).encode("utf-8") + b"\n"

            writer.write(encoded)
            await writer.drain()
        finally:
            writer.close()

            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass


class TrustedVerificationClient:
    def __init__(
        self,
        *,
        socket_path: Path,
        workspace_root: Path,
    ) -> None:
        self._socket_path = socket_path
        self._workspace_resolver = TrustedWorkspaceResolver(
            workspace_root=workspace_root,
        )

    async def verify(
        self,
        *,
        workspace: Path,
    ) -> VerificationResult:
        workspace_name = self._workspace_name(workspace)

        try:
            reader, writer = await asyncio.open_unix_connection(
                self._socket_path,
                limit=MAX_VERIFICATION_RESPONSE_BYTES + 1,
            )
        except OSError as exc:
            raise TrustedVerificationClientError("Unable to connect to trusted verifier.") from exc

        try:
            request = VerificationServiceRequest(
                workspace_name=workspace_name,
            )

            writer.write(serialize_verification_request(request).encode("utf-8") + b"\n")
            await writer.drain()

            try:
                raw = await reader.readline()
            except (
                asyncio.LimitOverrunError,
                ValueError,
            ) as exc:
                raise TrustedVerificationClientError(
                    "Trusted verifier response exceeded protocol limit."
                ) from exc

            if not raw or len(raw) > MAX_VERIFICATION_RESPONSE_BYTES or not raw.endswith(b"\n"):
                raise TrustedVerificationClientError(
                    "Trusted verifier returned an invalid response."
                )

            try:
                response = deserialize_verification_response(raw[:-1].decode("utf-8"))
            except (
                UnicodeDecodeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                raise TrustedVerificationClientError(
                    "Trusted verifier returned an invalid response."
                ) from exc

            if response.status is VerificationServiceStatus.ERROR:
                raise TrustedVerificationClientError(
                    f"Trusted verifier failed: {response.error_code}"
                )

            if response.result is None:
                raise TrustedVerificationClientError("Trusted verifier returned no result.")

            return response.result

        finally:
            writer.close()

            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    def _workspace_name(
        self,
        workspace: Path,
    ) -> str:
        try:
            expected = self._workspace_resolver.resolve(workspace.name)
        except TrustedWorkspaceError as exc:
            raise TrustedVerificationClientError(
                "Verification workspace is outside trusted root."
            ) from exc

        try:
            requested = workspace.resolve(strict=True)
        except FileNotFoundError as exc:
            raise TrustedVerificationClientError("Verification workspace does not exist.") from exc

        if requested != expected:
            raise TrustedVerificationClientError("Verification workspace is outside trusted root.")

        return expected.name


def _object(
    raw: str,
) -> dict[str, Any]:
    payload = json.loads(raw)

    if not isinstance(payload, dict):
        raise ValueError("Protocol payload must be an object.")

    return payload


def _verification_result(
    raw: Any,
) -> VerificationResult:
    if not isinstance(raw, dict):
        raise ValueError("Verification result must be an object.")

    if set(raw) != {
        "profile_version",
        "outcome",
        "reason_code",
        "steps",
    }:
        raise ValueError("Verification result contains invalid fields.")

    profile_version = raw["profile_version"]
    outcome_raw = raw["outcome"]
    reason_code = raw["reason_code"]
    steps_raw = raw["steps"]

    if not isinstance(profile_version, str):
        raise ValueError("profile_version must be a string.")

    if not isinstance(outcome_raw, str):
        raise ValueError("outcome must be a string.")

    if not isinstance(reason_code, str):
        raise ValueError("reason_code must be a string.")

    if not isinstance(steps_raw, list):
        raise ValueError("steps must be a list.")

    steps: list[VerificationStepResult] = []

    for raw_step in steps_raw:
        if not isinstance(raw_step, dict):
            raise ValueError("Verification step must be an object.")

        if set(raw_step) != {
            "check",
            "outcome",
            "exit_code",
            "summary",
        }:
            raise ValueError("Verification step contains invalid fields.")

        check_raw = raw_step["check"]
        step_outcome_raw = raw_step["outcome"]
        exit_code = raw_step["exit_code"]
        summary = raw_step["summary"]

        if not isinstance(check_raw, str):
            raise ValueError("check must be a string.")

        if not isinstance(step_outcome_raw, str):
            raise ValueError("step outcome must be a string.")

        if exit_code is not None and (
            isinstance(exit_code, bool) or not isinstance(exit_code, int)
        ):
            raise ValueError("exit_code must be an integer or null.")

        if not isinstance(summary, str):
            raise ValueError("summary must be a string.")

        steps.append(
            VerificationStepResult(
                check=VerificationCheck(check_raw),
                outcome=VerificationOutcome(step_outcome_raw),
                exit_code=exit_code,
                summary=summary,
            )
        )

    return VerificationResult(
        profile_version=profile_version,
        outcome=VerificationOutcome(outcome_raw),
        reason_code=reason_code,
        steps=tuple(steps),
    )
