from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from agent_platform.trust.change_set_identity import identify_change_set
from agent_platform.trust.change_set_materializer import (
    ChangeSetMaterializationError,
    MaterializedChangeSet,
)
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
    ChangeSetIdentityMismatchError,
    ChangeSetVerificationService,
    VerificationRejectedError,
    VerifiedChangeSet,
)
from agent_platform.trust.verification_profile import VerificationCheck


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


def _result(outcome: VerificationOutcome) -> VerificationResult:
    if outcome is VerificationOutcome.PASS:
        step = VerificationStepResult(
            check=VerificationCheck.SYNTAX,
            outcome=VerificationOutcome.PASS,
            exit_code=0,
            summary="pass",
        )
        reason = "all_checks_passed"
    elif outcome is VerificationOutcome.FAIL:
        step = VerificationStepResult(
            check=VerificationCheck.SYNTAX,
            outcome=VerificationOutcome.FAIL,
            exit_code=1,
            summary="fail",
        )
        reason = "check_failed"
    else:
        step = VerificationStepResult(
            check=VerificationCheck.SYNTAX,
            outcome=VerificationOutcome.ERROR,
            exit_code=None,
            summary="error",
        )
        reason = "verification_error"

    return VerificationResult(
        profile_version="m12-v0",
        outcome=outcome,
        reason_code=reason,
        steps=(step,),
    )


class RecordingMaterializer:
    def __init__(
        self,
        *,
        change_set: ChangeSet,
        workspace: Path,
        identity_override=None,
    ) -> None:
        identity = (
            identify_change_set(change_set) if identity_override is None else identity_override
        )
        self.materialized = MaterializedChangeSet(
            workspace=workspace,
            identity=identity,
            base_revision=change_set.base_revision,
        )
        self.assert_exact_calls = 0
        self.reject_postcondition = False

    @contextmanager
    def materialize(
        self,
        change_set: ChangeSet,
    ) -> Iterator[MaterializedChangeSet]:
        del change_set
        yield self.materialized

    def assert_exact(
        self,
        *,
        materialized: MaterializedChangeSet,
        change_set: ChangeSet,
    ) -> None:
        del materialized, change_set
        self.assert_exact_calls += 1

        if self.reject_postcondition:
            raise ChangeSetMaterializationError("verification workspace drifted")


class RecordingVerifier:
    def __init__(
        self,
        *,
        result: VerificationResult,
    ) -> None:
        self._result = result
        self.workspaces: list[Path] = []

    async def verify(
        self,
        *,
        workspace: Path,
    ) -> VerificationResult:
        self.workspaces.append(workspace)
        return self._result


@pytest.mark.asyncio
async def test_passing_verification_returns_identity_bound_token(
    tmp_path: Path,
) -> None:
    change_set = _change_set()
    materializer = RecordingMaterializer(
        change_set=change_set,
        workspace=tmp_path,
    )
    verifier = RecordingVerifier(
        result=_result(VerificationOutcome.PASS),
    )
    service = ChangeSetVerificationService(
        materializer=materializer,
        verifier=verifier,
    )

    verified = await service.verify(change_set)

    assert verified.change_set == change_set
    assert verified.identity == identify_change_set(change_set)
    assert verified.verification.outcome is VerificationOutcome.PASS
    assert materializer.assert_exact_calls == 1
    assert verifier.workspaces == [tmp_path]


@pytest.mark.asyncio
async def test_failed_verification_never_returns_verified_token(
    tmp_path: Path,
) -> None:
    change_set = _change_set()
    service = ChangeSetVerificationService(
        materializer=RecordingMaterializer(
            change_set=change_set,
            workspace=tmp_path,
        ),
        verifier=RecordingVerifier(
            result=_result(VerificationOutcome.FAIL),
        ),
    )

    with pytest.raises(VerificationRejectedError) as exc_info:
        await service.verify(change_set)

    assert exc_info.value.result.outcome is VerificationOutcome.FAIL


@pytest.mark.asyncio
async def test_post_verification_workspace_drift_fails_closed(
    tmp_path: Path,
) -> None:
    change_set = _change_set()
    materializer = RecordingMaterializer(
        change_set=change_set,
        workspace=tmp_path,
    )
    materializer.reject_postcondition = True
    service = ChangeSetVerificationService(
        materializer=materializer,
        verifier=RecordingVerifier(
            result=_result(VerificationOutcome.PASS),
        ),
    )

    with pytest.raises(
        ChangeSetMaterializationError,
        match="drifted",
    ):
        await service.verify(change_set)


@pytest.mark.asyncio
async def test_materialized_identity_mismatch_fails_before_verification(
    tmp_path: Path,
) -> None:
    change_set = _change_set()
    different = ChangeSet(
        base_revision=change_set.base_revision,
        branch_name="coding/different",
        commit_message=change_set.commit_message,
        changes=change_set.changes,
    )
    verifier = RecordingVerifier(
        result=_result(VerificationOutcome.PASS),
    )
    service = ChangeSetVerificationService(
        materializer=RecordingMaterializer(
            change_set=change_set,
            workspace=tmp_path,
            identity_override=identify_change_set(different),
        ),
        verifier=verifier,
    )

    with pytest.raises(ChangeSetIdentityMismatchError):
        await service.verify(change_set)

    assert verifier.workspaces == []


def test_verified_change_set_rejects_nonpassing_evidence() -> None:
    change_set = _change_set()

    with pytest.raises(ValueError, match="passing verification"):
        VerifiedChangeSet(
            change_set=change_set,
            identity=identify_change_set(change_set),
            verification=_result(VerificationOutcome.FAIL),
        )


def test_verified_change_set_rejects_identity_mismatch() -> None:
    change_set = _change_set()
    different = ChangeSet(
        base_revision=change_set.base_revision,
        branch_name="coding/different",
        commit_message=change_set.commit_message,
        changes=change_set.changes,
    )

    with pytest.raises(ValueError, match="identity"):
        VerifiedChangeSet(
            change_set=change_set,
            identity=identify_change_set(different),
            verification=_result(VerificationOutcome.PASS),
        )
