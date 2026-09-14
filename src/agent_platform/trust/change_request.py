from __future__ import annotations

import json
from typing import Any

from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
)


class ChangeRequestError(ValueError):
    pass


def serialize_change_set(change_set: ChangeSet) -> str:
    payload = {
        "version": 1,
        "base_revision": change_set.base_revision,
        "branch_name": change_set.branch_name,
        "commit_message": change_set.commit_message,
        "changes": [
            {
                "path": change.path,
                "operation": change.operation.value,
                "content": change.content,
            }
            for change in change_set.changes
        ],
    }

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )


def deserialize_change_set(raw: str) -> ChangeSet:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ChangeRequestError("Invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise ChangeRequestError("Change request must be an object.")

    expected_keys = {
        "version",
        "base_revision",
        "branch_name",
        "commit_message",
        "changes",
    }

    if set(payload) != expected_keys:
        raise ChangeRequestError("Change request contains missing or unexpected fields.")

    if payload["version"] != 1:
        raise ChangeRequestError("Unsupported change request version.")

    changes_payload = payload["changes"]

    if not isinstance(changes_payload, list):
        raise ChangeRequestError("changes must be a list.")

    changes: list[FileChange] = []

    for item in changes_payload:
        changes.append(_deserialize_file_change(item))

    try:
        return ChangeSet(
            base_revision=_require_string(
                payload["base_revision"],
                "base_revision",
            ),
            branch_name=_require_string(
                payload["branch_name"],
                "branch_name",
            ),
            commit_message=_require_string(
                payload["commit_message"],
                "commit_message",
            ),
            changes=tuple(changes),
        )
    except ValueError as exc:
        raise ChangeRequestError(str(exc)) from exc


def _deserialize_file_change(
    payload: Any,
) -> FileChange:
    if not isinstance(payload, dict):
        raise ChangeRequestError("Each change must be an object.")

    expected_keys = {
        "path",
        "operation",
        "content",
    }

    if set(payload) != expected_keys:
        raise ChangeRequestError("File change contains missing or unexpected fields.")

    path = _require_string(
        payload["path"],
        "path",
    )

    operation_raw = _require_string(
        payload["operation"],
        "operation",
    )

    try:
        operation = FileChangeOperation(operation_raw)
    except ValueError as exc:
        raise ChangeRequestError(f"Unsupported file operation: {operation_raw}") from exc

    content = payload["content"]

    if content is not None and not isinstance(content, str):
        raise ChangeRequestError("content must be a string or null.")

    try:
        return FileChange(
            path=path,
            operation=operation,
            content=content,
        )
    except ValueError as exc:
        raise ChangeRequestError(str(exc)) from exc


def _require_string(
    value: Any,
    field: str,
) -> str:
    if not isinstance(value, str):
        raise ChangeRequestError(f"{field} must be a string.")

    return value
