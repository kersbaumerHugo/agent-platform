from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent_platform.domain.work_item import WorkItem


def valid_payload() -> dict:
    return {
        "source": "github",
        "repository": "owner/repo",
        "issue_number": 1,
        "canonical_url": "https://github.com/owner/repo/issues/1",
        "updated_at": datetime.now(UTC),
        "title": "Example issue",
        "body": "Example body",
    }


def test_valid_work_item() -> None:
    item = WorkItem(**valid_payload())

    assert item.source == "github"
    assert item.repository == "owner/repo"
    assert item.issue_number == 1
    assert item.title == "Example issue"


def test_body_may_be_empty() -> None:
    payload = valid_payload()
    payload["body"] = ""

    item = WorkItem(**payload)

    assert item.body == ""


def test_updated_at_may_be_none() -> None:
    payload = valid_payload()
    payload["updated_at"] = None

    item = WorkItem(**payload)

    assert item.updated_at is None


@pytest.mark.parametrize(
    "field",
    [
        "source",
        "repository",
        "canonical_url",
        "title",
    ],
)
def test_required_string_rejects_empty_value(field: str) -> None:
    payload = valid_payload()
    payload[field] = ""

    with pytest.raises(ValidationError):
        WorkItem(**payload)


@pytest.mark.parametrize(
    "field",
    [
        "source",
        "repository",
        "canonical_url",
        "title",
    ],
)
def test_required_string_rejects_whitespace_only(field: str) -> None:
    payload = valid_payload()
    payload[field] = "   "

    with pytest.raises(ValidationError):
        WorkItem(**payload)


@pytest.mark.parametrize("issue_number", [0, -1])
def test_issue_number_must_be_positive(issue_number: int) -> None:
    payload = valid_payload()
    payload["issue_number"] = issue_number

    with pytest.raises(ValidationError):
        WorkItem(**payload)


def test_extra_fields_are_forbidden() -> None:
    payload = valid_payload()
    payload["provider_id"] = "github-specific-value"

    with pytest.raises(ValidationError):
        WorkItem(**payload)


def test_canonical_url_requires_string() -> None:
    payload = valid_payload()
    payload["canonical_url"] = 123

    with pytest.raises(ValidationError):
        WorkItem(**payload)


def test_work_item_is_immutable() -> None:
    item = WorkItem(**valid_payload())

    with pytest.raises(ValidationError):
        item.title = "Changed"
