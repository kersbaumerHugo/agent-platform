import pytest

from agent_platform.adapters.evaluation.work import WorkEvaluator
from agent_platform.application.run_agent import RunAgent
from agent_platform.application.work_orchestrator import WorkOrchestrator
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
)
from agent_platform.domain.models import (
    RuntimeRequest,
    RuntimeResult,
)
from agent_platform.domain.observability import ObservationEvent


class EvaluationRuntime:
    def __init__(
        self,
        *,
        fail_on_input: str | None = None,
    ) -> None:
        self.fail_on_input = fail_on_input

    @property
    def name(self) -> str:
        return "evaluation"

    async def execute(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResult:
        if request.input == self.fail_on_input:
            raise RuntimeError("planned evaluation failure")

        return RuntimeResult(
            output=f"{request.agent_id}:{request.input}",
        )


class NoopObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


def make_evaluator(
    *,
    fail_on_input: str | None = None,
) -> WorkEvaluator:
    runtime = EvaluationRuntime(
        fail_on_input=fail_on_input,
    )
    run_agent = RunAgent(
        runtime=runtime,
        observer=NoopObserver(),
    )
    orchestrator = WorkOrchestrator(
        run_agent=run_agent,
    )
    return WorkEvaluator(orchestrator)


@pytest.mark.asyncio
async def test_work_evaluator_passes_for_ordered_success() -> None:
    evaluator = make_evaluator()

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="ordered-success",
            input={
                "objective": "Draft and review.",
                "contexts": [
                    {
                        "role": "delivery",
                        "namespace": "app:linkedin",
                    },
                    {
                        "role": "subject",
                        "namespace": "project:homelab",
                    },
                ],
                "steps": [
                    {
                        "step_id": "draft",
                        "agent_id": "writer",
                        "input": "draft",
                    },
                    {
                        "step_id": "review",
                        "agent_id": "reviewer",
                        "input": "review",
                    },
                ],
            },
            expected={
                "status": "succeeded",
                "executed_step_ids": [
                    "draft",
                    "review",
                ],
                "run_statuses": [
                    "succeeded",
                    "succeeded",
                ],
                "failed_step_id": None,
                "contexts": [
                    {
                        "role": "delivery",
                        "namespace": "app:linkedin",
                    },
                    {
                        "role": "subject",
                        "namespace": "project:homelab",
                    },
                ],
            },
        )
    )

    assert result.outcome is EvaluationOutcome.PASS
    assert result.reason_code == "expectations_met"
    assert result.metrics["status_match"] == 1.0
    assert result.metrics["step_order_match"] == 1.0
    assert result.metrics["contexts_match"] == 1.0
    assert result.metrics["executed_step_count"] == 2.0


@pytest.mark.asyncio
async def test_work_evaluator_passes_for_stop_on_failure() -> None:
    evaluator = make_evaluator(
        fail_on_input="fail",
    )

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="stop-on-failure",
            input={
                "objective": "Stop after failure.",
                "steps": [
                    {
                        "step_id": "first",
                        "agent_id": "worker",
                        "input": "ok",
                    },
                    {
                        "step_id": "second",
                        "agent_id": "worker",
                        "input": "fail",
                    },
                    {
                        "step_id": "third",
                        "agent_id": "worker",
                        "input": "must-not-run",
                    },
                ],
            },
            expected={
                "status": "failed",
                "executed_step_ids": [
                    "first",
                    "second",
                ],
                "run_statuses": [
                    "succeeded",
                    "failed",
                ],
                "failed_step_id": "second",
                "contexts": [],
            },
        )
    )

    assert result.outcome is EvaluationOutcome.PASS
    assert result.metrics["executed_step_count"] == 2.0
    assert result.metrics["failed_step_match"] == 1.0
    assert result.metadata["actual_step_ids"] == [
        "first",
        "second",
    ]


@pytest.mark.asyncio
async def test_work_evaluator_fails_on_context_mismatch() -> None:
    evaluator = make_evaluator()

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="context-mismatch",
            input={
                "objective": "Write a homelab post.",
                "contexts": [
                    {
                        "role": "delivery",
                        "namespace": "app:linkedin",
                    },
                    {
                        "role": "subject",
                        "namespace": "project:homelab",
                    },
                ],
                "steps": [
                    {
                        "step_id": "draft",
                        "agent_id": "writer",
                        "input": "draft",
                    }
                ],
            },
            expected={
                "status": "succeeded",
                "executed_step_ids": [
                    "draft",
                ],
                "run_statuses": [
                    "succeeded",
                ],
                "failed_step_id": None,
                "contexts": [
                    {
                        "role": "delivery",
                        "namespace": "app:linkedin",
                    },
                    {
                        "role": "subject",
                        "namespace": "project:agent-platform",
                    },
                ],
            },
        )
    )

    assert result.outcome is EvaluationOutcome.FAIL
    assert result.reason_code == "expectation_mismatch"
    assert result.metrics["contexts_match"] == 0.0
