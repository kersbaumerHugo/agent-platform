from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agent_platform.adapters.workers.supervised_coding import (
    CodingSemanticReviewProtocolError,
    WorkerCodingSemanticReviewer,
)
from agent_platform.domain.coding import (
    CodingSemanticReviewDecision,
    CodingTask,
)
from agent_platform.trust.change_set_identity import identify_change_set
from agent_platform.trust.change_set_materializer import MaterializedChangeSet
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
from agent_platform.trust.verification_binding import VerifiedChangeSet
from agent_platform.trust.verification_profile import VerificationCheck
from agent_platform.worker.session import (
    WorkerExecutionRequest,
    WorkerExecutionResult,
)

BASE_REVISION = "a" * 40


def _task() -> CodingTask:
    return CodingTask(
        goal="Preserve behavior while adding semantic review.",
        expected_base_revision=BASE_REVISION,
    )


def _change_set() -> ChangeSet:
    return ChangeSet(
        base_revision=BASE_REVISION,
        branch_name="coding/test",
        commit_message="chore: semantic review test",
        changes=(
            FileChange(
                path="src/example.py",
                operation=FileChangeOperation.UPSERT,
                content="VALUE = 1\n",
            ),
        ),
    )


def _verified(change_set: ChangeSet) -> VerifiedChangeSet:
    return VerifiedChangeSet(
        change_set=change_set,
        identity=identify_change_set(change_set),
        verification=VerificationResult(
            profile_version="m12-v0",
            outcome=VerificationOutcome.PASS,
            reason_code="all_checks_passed",
            steps=(
                VerificationStepResult(
                    check=VerificationCheck.TEST,
                    outcome=VerificationOutcome.PASS,
                    exit_code=0,
                    summary="pass",
                ),
            ),
        ),
    )


@dataclass
class RecordingExecutor:
    summary: str
    requests: list[WorkerExecutionRequest] = field(default_factory=list)

    async def execute(
        self,
        request: WorkerExecutionRequest,
    ) -> WorkerExecutionResult:
        self.requests.append(request)
        return WorkerExecutionResult(summary=self.summary)


@dataclass
class RecordingMaterializer:
    workspace: Path
    fail_exact: bool = False
    materialized_inputs: list[ChangeSet] = field(default_factory=list)
    assert_exact_calls: int = 0

    @contextmanager
    def materialize(
        self,
        change_set: ChangeSet,
    ) -> Iterator[MaterializedChangeSet]:
        self.materialized_inputs.append(change_set)
        yield MaterializedChangeSet(
            workspace=self.workspace,
            identity=identify_change_set(change_set),
            base_revision=change_set.base_revision,
        )

    def assert_exact(
        self,
        *,
        materialized: MaterializedChangeSet,
        change_set: ChangeSet,
    ) -> None:
        del materialized, change_set
        self.assert_exact_calls += 1

        if self.fail_exact:
            raise RuntimeError("semantic reviewer mutated candidate")


@pytest.mark.asyncio
async def test_worker_semantic_reviewer_preserves_rejection_reasons(
    tmp_path: Path,
) -> None:
    change_set = _change_set()
    executor = RecordingExecutor(
        summary=('{"decision":"reject","reasons":["Unrelated tests were removed."]}')
    )
    materializer = RecordingMaterializer(workspace=tmp_path)
    reviewer = WorkerCodingSemanticReviewer(
        materializer=materializer,
        executor=executor,
    )

    result = await reviewer.review(
        task=_task(),
        verified=_verified(change_set),
    )

    assert result.decision is CodingSemanticReviewDecision.REJECT
    assert result.reasons == ("Unrelated tests were removed.",)
    assert materializer.assert_exact_calls == 1

    goal = executor.requests[0].goal

    assert "UNTRUSTED REVIEW EVIDENCE" in goal
    assert "duplicated special-case path" in goal
    assert "Return exactly one JSON object" in goal


@pytest.mark.asyncio
async def test_worker_semantic_reviewer_accepts_strict_approval_json(
    tmp_path: Path,
) -> None:
    materializer = RecordingMaterializer(workspace=tmp_path)
    reviewer = WorkerCodingSemanticReviewer(
        materializer=materializer,
        executor=RecordingExecutor(summary='{"decision":"approve","reasons":[]}'),
    )

    result = await reviewer.review(
        task=_task(),
        verified=_verified(_change_set()),
    )

    assert result.decision is CodingSemanticReviewDecision.APPROVE
    assert result.reasons == ()
    assert materializer.assert_exact_calls == 1


@pytest.mark.asyncio
async def test_worker_semantic_reviewer_rejects_malformed_json(
    tmp_path: Path,
) -> None:
    reviewer = WorkerCodingSemanticReviewer(
        materializer=RecordingMaterializer(workspace=tmp_path),
        executor=RecordingExecutor(summary="not-json"),
    )

    with pytest.raises(
        CodingSemanticReviewProtocolError,
        match="malformed JSON",
    ):
        await reviewer.review(
            task=_task(),
            verified=_verified(_change_set()),
        )


@pytest.mark.asyncio
async def test_worker_semantic_reviewer_rejects_invalid_contract(
    tmp_path: Path,
) -> None:
    reviewer = WorkerCodingSemanticReviewer(
        materializer=RecordingMaterializer(workspace=tmp_path),
        executor=RecordingExecutor(summary='{"decision":"reject","reasons":[]}'),
    )

    with pytest.raises(
        CodingSemanticReviewProtocolError,
        match="invalid review contract",
    ):
        await reviewer.review(
            task=_task(),
            verified=_verified(_change_set()),
        )


@pytest.mark.asyncio
async def test_worker_semantic_reviewer_detects_workspace_mutation(
    tmp_path: Path,
) -> None:
    materializer = RecordingMaterializer(
        workspace=tmp_path,
        fail_exact=True,
    )
    reviewer = WorkerCodingSemanticReviewer(
        materializer=materializer,
        executor=RecordingExecutor(summary='{"decision":"approve","reasons":[]}'),
    )

    with pytest.raises(
        RuntimeError,
        match="mutated candidate",
    ):
        await reviewer.review(
            task=_task(),
            verified=_verified(_change_set()),
        )

    assert materializer.assert_exact_calls == 1
