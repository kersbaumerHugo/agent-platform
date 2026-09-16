from datetime import datetime

import pytest
from pydantic import ValidationError

from agent_platform.domain.models import RunResult, RunStatus
from agent_platform.domain.work import (
    ContextRef,
    ContextRole,
    WorkRequest,
    WorkResult,
    WorkStatus,
    WorkStep,
    WorkStepResult,
)


def make_steps() -> list[WorkStep]:
    return [
        WorkStep(
            step_id="draft",
            agent_id="writer",
            input="Draft the post.",
        ),
        WorkStep(
            step_id="review",
            agent_id="reviewer",
            input="Review the post.",
        ),
    ]


def test_work_request_supports_explicit_cross_context_composition() -> None:
    request = WorkRequest(
        objective="Write a LinkedIn post about the homelab.",
        contexts=[
            ContextRef(
                role=ContextRole.SHARED,
                namespace="global",
            ),
            ContextRef(
                role=ContextRole.DELIVERY,
                namespace="app:linkedin",
            ),
            ContextRef(
                role=ContextRole.SUBJECT,
                namespace="project:homelab",
            ),
        ],
        steps=make_steps(),
    )

    assert request.objective == ("Write a LinkedIn post about the homelab.")
    assert [(context.role, context.namespace) for context in request.contexts] == [
        (ContextRole.SHARED, "global"),
        (ContextRole.DELIVERY, "app:linkedin"),
        (ContextRole.SUBJECT, "project:homelab"),
    ]


def test_work_request_requires_at_least_one_step() -> None:
    with pytest.raises(ValidationError):
        WorkRequest(
            objective="Do work.",
            steps=[],
        )


def test_work_request_rejects_duplicate_step_ids() -> None:
    with pytest.raises(
        ValidationError,
        match="step_id values must be unique",
    ):
        WorkRequest(
            objective="Do work.",
            steps=[
                WorkStep(
                    step_id="same",
                    agent_id="one",
                    input="First.",
                ),
                WorkStep(
                    step_id="same",
                    agent_id="two",
                    input="Second.",
                ),
            ],
        )


def test_work_request_rejects_duplicate_context_refs() -> None:
    with pytest.raises(
        ValidationError,
        match="contexts must be unique",
    ):
        WorkRequest(
            objective="Do work.",
            contexts=[
                ContextRef(
                    role=ContextRole.SUBJECT,
                    namespace="project:homelab",
                ),
                ContextRef(
                    role=ContextRole.SUBJECT,
                    namespace="project:homelab",
                ),
            ],
            steps=make_steps(),
        )


def test_context_roles_are_intentionally_small() -> None:
    assert list(ContextRole) == [
        ContextRole.SHARED,
        ContextRole.DELIVERY,
        ContextRole.SUBJECT,
    ]


def test_work_status_matches_v0_lifecycle() -> None:
    assert list(WorkStatus) == [
        WorkStatus.PENDING,
        WorkStatus.RUNNING,
        WorkStatus.SUCCEEDED,
        WorkStatus.FAILED,
    ]


def test_work_step_result_preserves_step_identity_and_run() -> None:
    run = RunResult(
        agent_id="writer",
        status=RunStatus.SUCCEEDED,
        output="draft",
    )
    result = WorkStepResult(
        step_id="draft",
        run=run,
    )

    assert result.step_id == "draft"
    assert result.run.run_id == run.run_id
    assert result.run.output == "draft"


def test_work_result_preserves_contexts_and_completed_step_results() -> None:
    context = ContextRef(
        role=ContextRole.SUBJECT,
        namespace="project:homelab",
    )
    run = RunResult(
        agent_id="writer",
        status=RunStatus.SUCCEEDED,
        output="draft",
    )

    result = WorkResult(
        status=WorkStatus.RUNNING,
        contexts=[context],
        step_results=[
            WorkStepResult(
                step_id="draft",
                run=run,
            )
        ],
    )

    assert result.work_id is not None
    assert result.status is WorkStatus.RUNNING
    assert result.contexts == [context]
    assert result.step_results[0].step_id == "draft"
    assert result.failed_step_id is None
    assert isinstance(result.started_at, datetime)
    assert result.finished_at is None
