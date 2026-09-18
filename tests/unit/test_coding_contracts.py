from uuid import UUID

import pytest
from pydantic import ValidationError

from agent_platform.domain.coding import CodingTask

TASK_ID = UUID("12000000-0000-4000-8000-000000000001")
BASE_REVISION = "b34272f84f7ff18d50a5a13c42155ae00b1591b0"


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
