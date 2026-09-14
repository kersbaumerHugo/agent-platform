from dataclasses import dataclass, field

import pytest

from agent_platform.trust.change_policy import ChangePolicy
from agent_platform.trust.publisher import (
    ChangeRejectedError,
    ChangeSet,
    FileChange,
    FileChangeOperation,
    PublicationResult,
    TrustedPublisher,
)


@dataclass
class FakeChangeSink:
    published: list[ChangeSet] = field(default_factory=list)

    async def publish(
        self,
        change_set: ChangeSet,
    ) -> PublicationResult:
        self.published.append(change_set)
        return PublicationResult(reference="fake://publication/1")


def make_change_set(*changes: FileChange) -> ChangeSet:
    return ChangeSet(
        base_revision="abc123",
        branch_name="agent/example-change",
        commit_message="feat: example change",
        changes=changes,
    )


@pytest.mark.asyncio
async def test_publishes_allowed_change() -> None:
    sink = FakeChangeSink()
    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=sink,
    )

    change_set = make_change_set(
        FileChange(
            path="src/agent_platform/application/example.py",
            operation=FileChangeOperation.UPSERT,
            content="VALUE = 42\n",
        )
    )

    result = await publisher.publish(change_set)

    assert result.reference == "fake://publication/1"
    assert sink.published == [change_set]


@pytest.mark.asyncio
async def test_rejected_change_never_reaches_sink() -> None:
    sink = FakeChangeSink()
    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=sink,
    )

    change_set = make_change_set(
        FileChange(
            path=".github/workflows/ci.yml",
            operation=FileChangeOperation.UPSERT,
            content="name: compromised\n",
        )
    )

    with pytest.raises(ChangeRejectedError) as exc_info:
        await publisher.publish(change_set)

    assert exc_info.value.decision.reason_code == "protected_path_modified"
    assert exc_info.value.decision.blocked_paths == (".github/workflows/ci.yml",)
    assert sink.published == []


@pytest.mark.asyncio
async def test_mixed_change_is_rejected_atomically() -> None:
    sink = FakeChangeSink()
    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=sink,
    )

    change_set = make_change_set(
        FileChange(
            path="src/agent_platform/application/example.py",
            operation=FileChangeOperation.UPSERT,
            content="VALUE = 42\n",
        ),
        FileChange(
            path="tests/trusted/test_change_policy.py",
            operation=FileChangeOperation.DELETE,
        ),
    )

    with pytest.raises(ChangeRejectedError):
        await publisher.publish(change_set)

    assert sink.published == []


def test_change_set_rejects_duplicate_paths() -> None:
    change = FileChange(
        path="src/example.py",
        operation=FileChangeOperation.UPSERT,
        content="x = 1\n",
    )

    with pytest.raises(ValueError, match="duplicate paths"):
        make_change_set(change, change)


def test_upsert_requires_content() -> None:
    with pytest.raises(ValueError, match="UPSERT requires content"):
        FileChange(
            path="src/example.py",
            operation=FileChangeOperation.UPSERT,
        )


def test_delete_rejects_content() -> None:
    with pytest.raises(ValueError, match="DELETE must not include content"):
        FileChange(
            path="src/example.py",
            operation=FileChangeOperation.DELETE,
            content="unexpected",
        )
