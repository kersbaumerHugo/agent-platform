from uuid import UUID

import pytest
from pydantic import ValidationError

from agent_platform.domain.coding import (
    CodingPublicationOutcome,
    CodingResult,
    CodingTask,
    CodingVerificationOutcome,
)

TASK_ID = UUID("12000000-0000-4000-8000-000000000001")
EXECUTION_ID = UUID("12000000-0000-4000-8000-00000000000a")
BASE_REVISION = "b34272f84f7ff18d50a5a13c42155ae00b1591b0"
CHANGE_SET_IDENTITY = f"v1:sha256:{'a' * 64}"


def make_task(**overrides: object) -> CodingTask:
    values: dict[str, object] = {
        "task_id": TASK_ID,
        "goal": "Add a focused deterministic unit test.",
        "expected_base_revision": BASE_REVISION,
    }
    values.update(overrides)

    return CodingTask.model_validate(values)


def test_coding_task_preserves_minimal_platform_owned_contract() -> None:
    task = make_task()

    assert task.task_id == TASK_ID
    assert task.goal == "Add a focused deterministic unit test."
    assert task.expected_base_revision == BASE_REVISION


def test_coding_task_rejects_blank_goal() -> None:
    with pytest.raises(
        ValidationError,
        match="goal must not be blank",
    ):
        make_task(goal="   ")


def test_coding_task_normalizes_goal_whitespace() -> None:
    task = make_task(
        goal="  Add a focused deterministic unit test.  ",
    )

    assert task.goal == "Add a focused deterministic unit test."


@pytest.mark.parametrize(
    "revision",
    [
        "",
        "main",
        "b34272f",
        "z" * 40,
        "b34272f84f7ff18d50a5a13c42155ae00b1591b00",
    ],
)
def test_coding_task_rejects_non_canonical_base_revision(
    revision: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="full 40-character Git SHA-1",
    ):
        make_task(expected_base_revision=revision)


def test_coding_task_normalizes_base_revision_to_lowercase() -> None:
    task = make_task(
        expected_base_revision=BASE_REVISION.upper(),
    )

    assert task.expected_base_revision == BASE_REVISION


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("repository_url", "https://example.invalid/repository.git"),
        ("base_branch", "other"),
        ("branch_name", "arbitrary-branch"),
        ("commit_message", "arbitrary commit"),
        ("verification_profile", "skip-tests"),
        ("contexts", []),
    ],
)
def test_coding_task_rejects_authority_fields_not_owned_by_request(
    field_name: str,
    field_value: object,
) -> None:
    with pytest.raises(
        ValidationError,
        match="Extra inputs are not permitted",
    ):
        make_task(**{field_name: field_value})


def test_coding_task_schema_contains_only_v0_request_fields() -> None:
    properties = CodingTask.model_json_schema()["properties"]

    assert list(properties) == [
        "task_id",
        "goal",
        "expected_base_revision",
    ]


def test_coding_task_serialization_is_deterministic() -> None:
    first = make_task()
    second = make_task()

    expected = (
        '{"task_id":"12000000-0000-4000-8000-000000000001",'
        '"goal":"Add a focused deterministic unit test.",'
        '"expected_base_revision":"b34272f84f7ff18d50a5a13c42155ae00b1591b0"}'
    )

    assert first.model_dump_json() == expected
    assert second.model_dump_json() == expected


def test_coding_task_is_immutable_after_validation() -> None:
    task = make_task()

    with pytest.raises(
        ValidationError,
        match="Instance is frozen",
    ):
        task.goal = "Replace the goal."


def make_result(**overrides: object) -> CodingResult:
    values: dict[str, object] = {
        "task_id": TASK_ID,
        "execution_id": EXECUTION_ID,
        "base_revision": BASE_REVISION,
        "change_set_identity": CHANGE_SET_IDENTITY,
        "changed_paths": (
            "tests/unit/test_z.py",
            "src/agent_platform/example.py",
        ),
        "verification_profile_version": "m12-v0",
        "verification_outcome": CodingVerificationOutcome.PASS,
        "publication_outcome": CodingPublicationOutcome.PUBLISHED,
        "publication_reference": ("https://github.com/kersbaumerHugo/agent-platform/pull/123"),
        "pull_request_number": 123,
    }
    values.update(overrides)
    return CodingResult.model_validate(values)


def test_coding_result_is_safe_deterministic_correlation_contract() -> None:
    result = make_result()

    assert result.task_id == TASK_ID
    assert result.execution_id == EXECUTION_ID
    assert result.base_revision == BASE_REVISION
    assert result.change_set_identity == CHANGE_SET_IDENTITY
    assert result.changed_paths == (
        "src/agent_platform/example.py",
        "tests/unit/test_z.py",
    )
    assert result.verification_profile_version == "m12-v0"
    assert result.verification_outcome is CodingVerificationOutcome.PASS
    assert result.publication_outcome is CodingPublicationOutcome.PUBLISHED
    assert result.pull_request_number == 123


def test_coding_result_rejects_invalid_change_set_identity() -> None:
    with pytest.raises(
        ValidationError,
        match="change_set_identity",
    ):
        make_result(change_set_identity="sha256:not-canonical")


def test_coding_result_rejects_duplicate_changed_paths() -> None:
    with pytest.raises(
        ValidationError,
        match="changed_paths must be unique",
    ):
        make_result(
            changed_paths=(
                "src/example.py",
                "src/example.py",
            )
        )


def test_coding_result_serialization_contains_no_raw_execution_material() -> None:
    serialized = make_result().model_dump_json()

    assert "goal" not in serialized
    assert "content" not in serialized
    assert "stdout" not in serialized
    assert "stderr" not in serialized
    assert "environment" not in serialized
