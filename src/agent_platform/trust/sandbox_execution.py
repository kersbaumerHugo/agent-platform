from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID


class SandboxExecutionRequestError(ValueError):
    pass


class SandboxExecutionResponseError(ValueError):
    pass


class TrustedWorkspaceError(ValueError):
    pass


class SandboxExecutionStatus(StrEnum):
    ACCEPTED = "accepted"
    ERROR = "error"


MAX_SANDBOX_SUMMARY_CHARS = 16 * 1024

_WORKSPACE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class SandboxExecutionRequest:
    execution_id: UUID
    workspace_name: str
    goal: str

    def __post_init__(self) -> None:
        workspace_name = self.workspace_name.strip()
        goal = self.goal.strip()

        if not workspace_name:
            raise ValueError("workspace_name must not be empty.")

        if not goal:
            raise ValueError("goal must not be empty.")

        object.__setattr__(self, "workspace_name", workspace_name)
        object.__setattr__(self, "goal", goal)


@dataclass(frozen=True)
class SandboxExecutionResponse:
    status: SandboxExecutionStatus
    execution_id: UUID | None
    summary: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.status is SandboxExecutionStatus.ACCEPTED:
            if self.execution_id is None:
                raise ValueError("Accepted sandbox responses require execution_id.")

            if self.summary is None:
                raise ValueError("Accepted sandbox responses require summary.")

            if self.error_code is not None:
                raise ValueError("Accepted sandbox responses must not include error_code.")
        else:
            if self.summary is not None:
                raise ValueError("Error sandbox responses must not include summary.")

            if self.error_code is None or not self.error_code.strip():
                raise ValueError("Error sandbox responses require error_code.")

            object.__setattr__(
                self,
                "error_code",
                self.error_code.strip(),
            )

        if self.summary is not None and len(self.summary) > MAX_SANDBOX_SUMMARY_CHARS:
            raise ValueError("Sandbox response summary exceeds the protocol limit.")


def serialize_sandbox_execution_request(
    request: SandboxExecutionRequest,
) -> str:
    payload = {
        "version": 1,
        "execution_id": str(request.execution_id),
        "workspace_name": request.workspace_name,
        "goal": request.goal,
    }

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )


def deserialize_sandbox_execution_request(
    raw: str,
) -> SandboxExecutionRequest:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SandboxExecutionRequestError("Invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise SandboxExecutionRequestError("Sandbox execution request must be an object.")

    expected_keys = {
        "version",
        "execution_id",
        "workspace_name",
        "goal",
    }

    if set(payload) != expected_keys:
        raise SandboxExecutionRequestError(
            "Sandbox execution request contains missing or unexpected fields."
        )

    if payload["version"] != 1:
        raise SandboxExecutionRequestError("Unsupported sandbox execution request version.")

    execution_id_raw = _require_request_string(
        payload["execution_id"],
        "execution_id",
    )
    workspace_name = _require_request_string(
        payload["workspace_name"],
        "workspace_name",
    )
    goal = _require_request_string(
        payload["goal"],
        "goal",
    )

    try:
        execution_id = UUID(execution_id_raw)
    except ValueError as exc:
        raise SandboxExecutionRequestError("execution_id must be a valid UUID.") from exc

    try:
        return SandboxExecutionRequest(
            execution_id=execution_id,
            workspace_name=workspace_name,
            goal=goal,
        )
    except ValueError as exc:
        raise SandboxExecutionRequestError(str(exc)) from exc


def serialize_sandbox_execution_response(
    response: SandboxExecutionResponse,
) -> str:
    payload = {
        "version": 1,
        "status": response.status.value,
        "execution_id": (str(response.execution_id) if response.execution_id is not None else None),
        "summary": response.summary,
        "error_code": response.error_code,
    }

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )


def deserialize_sandbox_execution_response(
    raw: str,
) -> SandboxExecutionResponse:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SandboxExecutionResponseError("Invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise SandboxExecutionResponseError("Sandbox execution response must be an object.")

    expected_keys = {
        "version",
        "status",
        "execution_id",
        "summary",
        "error_code",
    }

    if set(payload) != expected_keys:
        raise SandboxExecutionResponseError(
            "Sandbox execution response contains missing or unexpected fields."
        )

    if payload["version"] != 1:
        raise SandboxExecutionResponseError("Unsupported sandbox execution response version.")

    status_raw = payload["status"]

    if not isinstance(status_raw, str):
        raise SandboxExecutionResponseError("status must be a string.")

    try:
        status = SandboxExecutionStatus(status_raw)
    except ValueError as exc:
        raise SandboxExecutionResponseError(
            "Unsupported sandbox execution response status."
        ) from exc

    execution_id_raw = payload["execution_id"]

    if execution_id_raw is None:
        execution_id = None
    elif isinstance(execution_id_raw, str):
        try:
            execution_id = UUID(execution_id_raw)
        except ValueError as exc:
            raise SandboxExecutionResponseError(
                "execution_id must be a valid UUID or null."
            ) from exc
    else:
        raise SandboxExecutionResponseError("execution_id must be a string or null.")

    summary = _optional_response_string(
        payload["summary"],
        "summary",
    )
    error_code = _optional_response_string(
        payload["error_code"],
        "error_code",
    )

    try:
        return SandboxExecutionResponse(
            status=status,
            execution_id=execution_id,
            summary=summary,
            error_code=error_code,
        )
    except ValueError as exc:
        raise SandboxExecutionResponseError(str(exc)) from exc


class TrustedWorkspaceResolver:
    """Resolve a sandbox workspace below one trusted root."""

    def __init__(
        self,
        *,
        workspace_root: Path,
    ) -> None:
        if workspace_root.is_symlink():
            raise TrustedWorkspaceError("workspace_root must not be a symlink.")

        try:
            resolved_root = workspace_root.resolve(strict=True)
        except FileNotFoundError as exc:
            raise TrustedWorkspaceError("workspace_root must exist.") from exc

        if not resolved_root.is_dir():
            raise TrustedWorkspaceError("workspace_root must be a directory.")

        self._workspace_root = resolved_root

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def resolve(
        self,
        workspace_name: str,
    ) -> Path:
        name = workspace_name.strip()

        if not _WORKSPACE_NAME_PATTERN.fullmatch(name):
            raise TrustedWorkspaceError("workspace_name is not a valid direct-child name.")

        if name in {".", ".."}:
            raise TrustedWorkspaceError("workspace_name must not be a traversal segment.")

        candidate = self._workspace_root / name

        if candidate.is_symlink():
            raise TrustedWorkspaceError("workspace must not be a symlink.")

        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise TrustedWorkspaceError("workspace does not exist.") from exc

        if not resolved.is_dir():
            raise TrustedWorkspaceError("workspace must be a directory.")

        if resolved.parent != self._workspace_root:
            raise TrustedWorkspaceError("workspace must be a direct child of workspace_root.")

        return resolved


def _require_request_string(
    value: Any,
    field: str,
) -> str:
    if not isinstance(value, str):
        raise SandboxExecutionRequestError(f"{field} must be a string.")

    return value


def _optional_response_string(
    value: Any,
    field: str,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise SandboxExecutionResponseError(f"{field} must be a string or null.")

    return value
