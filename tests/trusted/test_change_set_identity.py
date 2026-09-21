from __future__ import annotations

from dataclasses import replace

import pytest

from agent_platform.trust.change_set_identity import (
    ChangeSetIdentity,
    identify_change_set,
)
from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
)


def _change_set(
    *,
    changes: tuple[FileChange, ...] | None = None,
) -> ChangeSet:
    return ChangeSet(
        base_revision="a" * 40,
        branch_name="coding/task-123",
        commit_message="chore: apply supervised coding task",
        changes=changes
        if changes is not None
        else (
            FileChange(
                path="src/example.py",
                operation=FileChangeOperation.UPSERT,
                content="VALUE = 1\n",
            ),
        ),
    )


def test_identity_is_deterministic() -> None:
    change_set = _change_set()

    first = identify_change_set(change_set)
    second = identify_change_set(change_set)

    assert first == second
    assert first.reference == f"v1:sha256:{first.sha256}"


def test_identity_is_stable_across_change_order() -> None:
    first_change = FileChange(
        path="src/a.py",
        operation=FileChangeOperation.UPSERT,
        content="A = 1\n",
    )
    second_change = FileChange(
        path="src/b.py",
        operation=FileChangeOperation.DELETE,
    )

    first = identify_change_set(
        _change_set(
            changes=(
                first_change,
                second_change,
            )
        )
    )
    second = identify_change_set(
        _change_set(
            changes=(
                second_change,
                first_change,
            )
        )
    )

    assert first == second


def test_identity_changes_when_file_content_changes() -> None:
    original = _change_set()
    changed = _change_set(
        changes=(
            FileChange(
                path="src/example.py",
                operation=FileChangeOperation.UPSERT,
                content="VALUE = 2\n",
            ),
        )
    )

    assert identify_change_set(original) != identify_change_set(changed)


def test_identity_binds_base_and_publication_metadata() -> None:
    original = _change_set()
    original_identity = identify_change_set(original)

    assert (
        identify_change_set(
            replace(
                original,
                base_revision="b" * 40,
            )
        )
        != original_identity
    )

    assert (
        identify_change_set(
            replace(
                original,
                branch_name="coding/different-task",
            )
        )
        != original_identity
    )

    assert (
        identify_change_set(
            replace(
                original,
                commit_message="different message",
            )
        )
        != original_identity
    )


def test_identity_rejects_noncanonical_digest() -> None:
    with pytest.raises(ValueError):
        ChangeSetIdentity(
            version="v1",
            sha256="A" * 64,
        )

    with pytest.raises(ValueError):
        ChangeSetIdentity(
            version="v2",
            sha256="a" * 64,
        )
