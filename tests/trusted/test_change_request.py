import json

import pytest

from agent_platform.trust.change_request import (
    ChangeRequestError,
    deserialize_change_set,
    serialize_change_set,
)
from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
)


def example_change_set() -> ChangeSet:
    return ChangeSet(
        base_revision="abc123",
        branch_name="agent/example",
        commit_message="feat: example",
        changes=(
            FileChange(
                path="src/example.py",
                operation=FileChangeOperation.UPSERT,
                content="VALUE = 42\n",
            ),
            FileChange(
                path="docs/old.md",
                operation=FileChangeOperation.DELETE,
            ),
        ),
    )


def test_round_trip() -> None:
    original = example_change_set()

    encoded = serialize_change_set(original)
    decoded = deserialize_change_set(encoded)

    assert decoded == original


def test_serialization_is_deterministic() -> None:
    change_set = example_change_set()

    assert serialize_change_set(change_set) == serialize_change_set(change_set)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not-json",
        "[]",
        "{}",
    ],
)
def test_rejects_invalid_envelope(
    raw: str,
) -> None:
    with pytest.raises(ChangeRequestError):
        deserialize_change_set(raw)


def test_rejects_unknown_top_level_field() -> None:
    payload = json.loads(serialize_change_set(example_change_set()))

    payload["admin"] = True

    with pytest.raises(
        ChangeRequestError,
        match="unexpected fields",
    ):
        deserialize_change_set(json.dumps(payload))


def test_rejects_unknown_file_change_field() -> None:
    payload = json.loads(serialize_change_set(example_change_set()))

    payload["changes"][0]["bypass"] = True

    with pytest.raises(
        ChangeRequestError,
        match="unexpected fields",
    ):
        deserialize_change_set(json.dumps(payload))


def test_rejects_unknown_operation() -> None:
    payload = json.loads(serialize_change_set(example_change_set()))

    payload["changes"][0]["operation"] = "chmod"

    with pytest.raises(
        ChangeRequestError,
        match="Unsupported file operation",
    ):
        deserialize_change_set(json.dumps(payload))


def test_rejects_future_protocol_version() -> None:
    payload = json.loads(serialize_change_set(example_change_set()))

    payload["version"] = 2

    with pytest.raises(
        ChangeRequestError,
        match="Unsupported change request version",
    ):
        deserialize_change_set(json.dumps(payload))
