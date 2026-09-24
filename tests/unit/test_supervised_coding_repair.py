from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import pytest

from agent_platform.adapters.workers.supervised_coding import (
    WorkerCodingRepairProducer,
)
from agent_platform.application.supervised_coding import PreparedCodingTask
from agent_platform.application.supervised_coding_publication import (
    CodingRepairBaseRevisionMismatchError,
    CodingRepairNoChangeError,
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

TASK_ID = UUID("22000000-0000-4000-8000-000000000001")
EXECUTION_ID = UUID("22000000-0000-4000-8000-000000000002")
BASE_REVISION = "a" * 40
OTHER_REVISION = "b" * 40


def _task() -> CodingTask:
    return CodingTask(
        task_id=TASK_ID,
        goal="Implement the requested focused change.",
        expected_base_revision=BASE_REVISION,
    )


def _change_set(
    version: int,
    *,
    base_revision: str = BASE_REVISION,
) -> ChangeSet:
    return ChangeSet(
        base_revision=base_revision,
        branch_name=f"coding/{TASK_ID}",
        commit_message=f"chore: apply supervised coding task {TASK_ID}",
        changes=(
            FileChange(
                path="src/example.py",
                operation=FileChangeOperation.UPSERT,
                content=f"VALUE = {version}\n",
            ),
        ),
    )


def _passing_result() -> VerificationResult:
    return VerificationResult(
        profile_version="m12-v0",
        outcome=VerificationOutcome.PASS,
        reason_code="all_checks_passed",
        steps=(
            VerificationStepResult(
                check=VerificationCheck.SYNTAX,
                outcome=VerificationOutcome.PASS,
                exit_code=0,
                summary="verification_step_passed",
            ),
        ),
    )


def _failing_result() -> VerificationResult:
    return VerificationResult(
        profile_version="m12-v0",
        outcome=VerificationOutcome.FAIL,
        reason_code="check_failed",
        steps=(
            VerificationStepResult(
                check=VerificationCheck.SYNTAX,
                outcome=VerificationOutcome.PASS,
                exit_code=0,
                summary="verification_step_passed",
            ),
            VerificationStepResult(
                check=VerificationCheck.RUFF_LINT,
                outcome=VerificationOutcome.FAIL,
                exit_code=1,
                summary="verification_step_failed",
            ),
        ),
    )


def _verified(change_set: ChangeSet) -> VerifiedChangeSet:
    return VerifiedChangeSet(
        change_set=change_set,
        identity=identify_change_set(change_set),
        verification=_passing_result(),
    )


@dataclass
class FixedPreparation:
    change_set: ChangeSet

    async def execute(
        self,
        task: CodingTask,
    ) -> PreparedCodingTask:
        return PreparedCodingTask(
            task_id=task.task_id,
            execution_id=EXECUTION_ID,
            change_set=self.change_set,
        )


@dataclass
class SequenceVerification:
    outcomes: list[VerificationOutcome]
    change_sets: list[ChangeSet] = field(default_factory=list)

    async def verify(
        self,
        change_set: ChangeSet,
    ) -> VerifiedChangeSet:
        self.change_sets.append(change_set)
        outcome = self.outcomes.pop(0)

        if outcome is VerificationOutcome.PASS:
            return _verified(change_set)

        raise VerificationRejectedError(_failing_result())


@dataclass
class SequenceRepairer:
    candidates: list[ChangeSet]
    calls: list[tuple[ChangeSet, VerificationResult, int]] = field(default_factory=list)

    async def repair(
        self,
        *,
        task: CodingTask,
        candidate: ChangeSet,
        verification: VerificationResult,
        attempt: int,
    ) -> ChangeSet:
        assert task == _task()
        self.calls.append(
            (
                candidate,
                verification,
                attempt,
            )
        )
        return self.candidates.pop(0)


@dataclass
class RecordingPublisher:
    verified_inputs: list[VerifiedChangeSet] = field(default_factory=list)

    async def publish(
        self,
        verified: VerifiedChangeSet,
    ) -> VerifiedPublicationResult:
        self.verified_inputs.append(verified)
        return VerifiedPublicationResult(
            reference="https://github.com/kersbaumerHugo/agent-platform/pull/123",
            identity=verified.identity,
        )


def _service(
    *,
    outcomes: list[VerificationOutcome],
    repairs: list[ChangeSet],
) -> tuple[
    SupervisedCodingPublicationService,
    SequenceVerification,
    SequenceRepairer,
    RecordingPublisher,
]:
    initial = _change_set(0)
    verification = SequenceVerification(outcomes=outcomes)
    repairer = SequenceRepairer(candidates=repairs)
    publisher = RecordingPublisher()

    service = SupervisedCodingPublicationService(
        preparation=FixedPreparation(initial),
        verification=verification,
        repairer=repairer,
        publisher=publisher,
    )

    return (
        service,
        verification,
        repairer,
        publisher,
    )


@pytest.mark.asyncio
async def test_initial_pass_does_not_repair() -> None:
    service, verification, repairer, publisher = _service(
        outcomes=[VerificationOutcome.PASS],
        repairs=[],
    )

    result = await service.execute(_task())

    assert result.change_set_identity == identify_change_set(_change_set(0)).reference
    assert verification.change_sets == [_change_set(0)]
    assert repairer.calls == []
    assert len(publisher.verified_inputs) == 1
    assert publisher.verified_inputs[0].change_set == _change_set(0)


@pytest.mark.asyncio
async def test_one_repair_then_pass_publishes_only_repaired_candidate() -> None:
    repaired = _change_set(1)
    service, verification, repairer, publisher = _service(
        outcomes=[
            VerificationOutcome.FAIL,
            VerificationOutcome.PASS,
        ],
        repairs=[repaired],
    )

    result = await service.execute(_task())

    assert verification.change_sets == [
        _change_set(0),
        repaired,
    ]
    assert [call[2] for call in repairer.calls] == [1]
    assert result.change_set_identity == identify_change_set(repaired).reference
    assert [item.change_set for item in publisher.verified_inputs] == [repaired]


@pytest.mark.asyncio
async def test_two_repairs_then_pass_is_bounded_and_publishable() -> None:
    first_repair = _change_set(1)
    second_repair = _change_set(2)

    service, verification, repairer, publisher = _service(
        outcomes=[
            VerificationOutcome.FAIL,
            VerificationOutcome.FAIL,
            VerificationOutcome.PASS,
        ],
        repairs=[
            first_repair,
            second_repair,
        ],
    )

    result = await service.execute(_task())

    assert verification.change_sets == [
        _change_set(0),
        first_repair,
        second_repair,
    ]
    assert [call[2] for call in repairer.calls] == [1, 2]
    assert result.change_set_identity == identify_change_set(second_repair).reference
    assert [item.change_set for item in publisher.verified_inputs] == [second_repair]


@pytest.mark.asyncio
async def test_three_failed_verifications_stop_after_exactly_two_repairs() -> None:
    first_repair = _change_set(1)
    second_repair = _change_set(2)

    service, verification, repairer, publisher = _service(
        outcomes=[
            VerificationOutcome.FAIL,
            VerificationOutcome.FAIL,
            VerificationOutcome.FAIL,
        ],
        repairs=[
            first_repair,
            second_repair,
        ],
    )

    with pytest.raises(VerificationRejectedError):
        await service.execute(_task())

    assert verification.change_sets == [
        _change_set(0),
        first_repair,
        second_repair,
    ]
    assert [call[2] for call in repairer.calls] == [1, 2]
    assert publisher.verified_inputs == []


@pytest.mark.asyncio
async def test_repair_that_does_not_change_candidate_fails_closed() -> None:
    initial = _change_set(0)
    service, verification, repairer, publisher = _service(
        outcomes=[VerificationOutcome.FAIL],
        repairs=[initial],
    )

    with pytest.raises(
        CodingRepairNoChangeError,
        match="did not change",
    ):
        await service.execute(_task())

    assert verification.change_sets == [initial]
    assert len(repairer.calls) == 1
    assert publisher.verified_inputs == []


@pytest.mark.asyncio
async def test_repair_must_preserve_trusted_base_revision() -> None:
    wrong_base = _change_set(
        1,
        base_revision=OTHER_REVISION,
    )
    service, verification, repairer, publisher = _service(
        outcomes=[VerificationOutcome.FAIL],
        repairs=[wrong_base],
    )

    with pytest.raises(
        CodingRepairBaseRevisionMismatchError,
        match="trusted base revision",
    ):
        await service.execute(_task())

    assert verification.change_sets == [_change_set(0)]
    assert len(repairer.calls) == 1
    assert publisher.verified_inputs == []


def test_repair_goal_contains_failed_authoritative_command() -> None:
    goal = WorkerCodingRepairProducer._build_repair_goal(
        task=_task(),
        verification=_failing_result(),
        attempt=1,
    )

    assert "bounded repair attempt 1" in goal
    assert "ruff_lint" in goal
    assert "python -m ruff check src tests scripts" in goal
    assert "syntax:" not in goal
    assert "git status --short" in goal
