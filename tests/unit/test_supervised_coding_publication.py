from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import pytest

from agent_platform.application.supervised_coding import PreparedCodingTask
from agent_platform.application.supervised_coding_publication import (
    CodingPublicationIdentityMismatchError,
    SupervisedCodingPublicationService,
)
from agent_platform.domain.coding import CodingTask
from agent_platform.trust.change_set_identity import identify_change_set
from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
)
from agent_platform.trust.verification import (
    VerificationOutcome,
    VerificationResult,
    VerificationStepResult,
)
from agent_platform.trust.verification_binding import (
    VerificationRejectedError,
    VerifiedChangeSet,
)
from agent_platform.trust.verification_profile import VerificationCheck
from agent_platform.trust.verified_publication import VerifiedPublicationResult

TASK_ID = UUID("12000000-0000-4000-8000-000000000006")
BASE_REVISION = "a" * 40


def _task() -> CodingTask:
    return CodingTask(
        task_id=TASK_ID,
        goal="Publish only an authoritatively verified coding change.",
        expected_base_revision=BASE_REVISION,
    )


def _change_set() -> ChangeSet:
    return ChangeSet(
        base_revision=BASE_REVISION,
        branch_name=f"coding/{TASK_ID}",
        commit_message=f"chore: apply supervised coding task {TASK_ID}",
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


def _verified(change_set: ChangeSet) -> VerifiedChangeSet:
    return VerifiedChangeSet(
        change_set=change_set,
        identity=identify_change_set(change_set),
        verification=_passing_verification(),
    )


@dataclass
class RecordingPreparation:
    prepared: PreparedCodingTask
    tasks: list[CodingTask] = field(default_factory=list)

    async def execute(
        self,
        task: CodingTask,
    ) -> PreparedCodingTask:
        self.tasks.append(task)
        return self.prepared


@dataclass
class RecordingVerification:
    verified: VerifiedChangeSet
    change_sets: list[ChangeSet] = field(default_factory=list)

    async def verify(
        self,
        change_set: ChangeSet,
    ) -> VerifiedChangeSet:
        self.change_sets.append(change_set)
        return self.verified


@dataclass
class RecordingPublisher:
    result: VerifiedPublicationResult
    verified_inputs: list[VerifiedChangeSet] = field(default_factory=list)

    async def publish(
        self,
        verified: VerifiedChangeSet,
    ) -> VerifiedPublicationResult:
        self.verified_inputs.append(verified)
        return self.result


@pytest.mark.asyncio
async def test_supervised_flow_publishes_only_verified_change_set() -> None:
    task = _task()
    change_set = _change_set()
    verified = _verified(change_set)
    preparation = RecordingPreparation(
        prepared=PreparedCodingTask(
            task_id=TASK_ID,
            change_set=change_set,
        )
    )
    verification = RecordingVerification(
        verified=verified,
    )
    publisher = RecordingPublisher(
        result=VerifiedPublicationResult(
            reference="pr:https://example.invalid/pull/123",
            identity=verified.identity,
        )
    )
    service = SupervisedCodingPublicationService(
        preparation=preparation,
        verification=verification,
        publisher=publisher,
    )

    result = await service.execute(task)

    assert result.reference == "pr:https://example.invalid/pull/123"
    assert result.identity == verified.identity
    assert preparation.tasks == [task]
    assert verification.change_sets == [change_set]
    assert publisher.verified_inputs == [verified]


@pytest.mark.asyncio
async def test_verification_rejection_blocks_publication() -> None:
    task = _task()
    change_set = _change_set()
    preparation = RecordingPreparation(
        prepared=PreparedCodingTask(
            task_id=TASK_ID,
            change_set=change_set,
        )
    )

    class RejectingVerification:
        async def verify(
            self,
            requested: ChangeSet,
        ) -> VerifiedChangeSet:
            assert requested == change_set

            failed = VerificationResult(
                profile_version="m12-v0",
                outcome=VerificationOutcome.FAIL,
                reason_code="check_failed",
                steps=(
                    VerificationStepResult(
                        check=VerificationCheck.SYNTAX,
                        outcome=VerificationOutcome.FAIL,
                        exit_code=1,
                        summary="fail",
                    ),
                ),
            )
            raise VerificationRejectedError(failed)

    publisher = RecordingPublisher(
        result=VerifiedPublicationResult(
            reference="must-not-be-used",
            identity=identify_change_set(change_set),
        )
    )
    service = SupervisedCodingPublicationService(
        preparation=preparation,
        verification=RejectingVerification(),
        publisher=publisher,
    )

    with pytest.raises(VerificationRejectedError):
        await service.execute(task)

    assert publisher.verified_inputs == []


@pytest.mark.asyncio
async def test_publication_identity_mismatch_fails_closed() -> None:
    task = _task()
    change_set = _change_set()
    verified = _verified(change_set)
    different = ChangeSet(
        base_revision=change_set.base_revision,
        branch_name="coding/different",
        commit_message=change_set.commit_message,
        changes=change_set.changes,
    )
    service = SupervisedCodingPublicationService(
        preparation=RecordingPreparation(
            prepared=PreparedCodingTask(
                task_id=TASK_ID,
                change_set=change_set,
            )
        ),
        verification=RecordingVerification(
            verified=verified,
        ),
        publisher=RecordingPublisher(
            result=VerifiedPublicationResult(
                reference="pr:https://example.invalid/pull/123",
                identity=identify_change_set(different),
            )
        ),
    )

    with pytest.raises(
        CodingPublicationIdentityMismatchError,
        match="does not match verified",
    ):
        await service.execute(task)


@pytest.mark.asyncio
async def test_preparation_failure_stops_verification_and_publication() -> None:
    task = _task()
    change_set = _change_set()
    verified = _verified(change_set)

    class FailingPreparation:
        async def execute(
            self,
            requested: CodingTask,
        ) -> PreparedCodingTask:
            assert requested == task
            raise RuntimeError("preparation failed")

    verification = RecordingVerification(
        verified=verified,
    )
    publisher = RecordingPublisher(
        result=VerifiedPublicationResult(
            reference="must-not-be-used",
            identity=verified.identity,
        )
    )
    service = SupervisedCodingPublicationService(
        preparation=FailingPreparation(),
        verification=verification,
        publisher=publisher,
    )

    with pytest.raises(
        RuntimeError,
        match="preparation failed",
    ):
        await service.execute(task)

    assert verification.change_sets == []
    assert publisher.verified_inputs == []
