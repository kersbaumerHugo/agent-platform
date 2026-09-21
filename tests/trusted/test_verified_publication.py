from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from agent_platform.trust.change_set_identity import identify_change_set
from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
    PublicationResult,
)
from agent_platform.trust.verification import (
    VerificationOutcome,
    VerificationResult,
    VerificationStepResult,
)
from agent_platform.trust.verification_binding import VerifiedChangeSet
from agent_platform.trust.verification_profile import VerificationCheck
from agent_platform.trust.verified_publication import (
    VerifiedChangePublisher,
    VerifiedPublicationIdentityMismatchError,
)


def _change_set() -> ChangeSet:
    return ChangeSet(
        base_revision="a" * 40,
        branch_name="coding/task-123",
        commit_message="chore: supervised change",
        changes=(
            FileChange(
                path="src/example.py",
                operation=FileChangeOperation.UPSERT,
                content="VALUE = 1\n",
            ),
        ),
    )


def _passing_verification() -> VerificationResult:
    return VerificationResult(
        profile_version="m12-v0",
        outcome=VerificationOutcome.PASS,
        reason_code="all_checks_passed",
        steps=(
            VerificationStepResult(
                check=VerificationCheck.SYNTAX,
                outcome=VerificationOutcome.PASS,
                exit_code=0,
                summary="pass",
            ),
        ),
    )


def _verified_change_set() -> VerifiedChangeSet:
    change_set = _change_set()

    return VerifiedChangeSet(
        change_set=change_set,
        identity=identify_change_set(change_set),
        verification=_passing_verification(),
    )


@dataclass
class RecordingPublisher:
    published: list[ChangeSet] = field(default_factory=list)

    async def publish(
        self,
        change_set: ChangeSet,
    ) -> PublicationResult:
        self.published.append(change_set)
        return PublicationResult(
            reference="pr:https://example.invalid/pull/123",
        )


@pytest.mark.asyncio
async def test_publishes_exact_verified_change_set_object() -> None:
    verified = _verified_change_set()
    delegate = RecordingPublisher()
    publisher = VerifiedChangePublisher(
        publisher=delegate,
    )

    result = await publisher.publish(verified)

    assert len(delegate.published) == 1
    assert delegate.published[0] is verified.change_set
    assert result.reference == "pr:https://example.invalid/pull/123"
    assert result.identity == verified.identity


@pytest.mark.asyncio
async def test_rejects_identity_drift_before_publication() -> None:
    verified = _verified_change_set()
    delegate = RecordingPublisher()
    publisher = VerifiedChangePublisher(
        publisher=delegate,
    )

    object.__setattr__(
        verified.change_set,
        "branch_name",
        "coding/tampered",
    )

    with pytest.raises(
        VerifiedPublicationIdentityMismatchError,
        match="identity changed",
    ):
        await publisher.publish(verified)

    assert delegate.published == []


@pytest.mark.asyncio
async def test_delegate_failure_is_not_converted_to_success() -> None:
    class FailingPublisher:
        async def publish(
            self,
            change_set: ChangeSet,
        ) -> PublicationResult:
            del change_set
            raise RuntimeError("publication failed")

    publisher = VerifiedChangePublisher(
        publisher=FailingPublisher(),
    )

    with pytest.raises(
        RuntimeError,
        match="publication failed",
    ):
        await publisher.publish(_verified_change_set())


def test_verified_publication_result_requires_reference() -> None:
    from agent_platform.trust.verified_publication import (
        VerifiedPublicationResult,
    )

    verified = _verified_change_set()

    with pytest.raises(ValueError, match="reference"):
        VerifiedPublicationResult(
            reference="",
            identity=verified.identity,
        )
