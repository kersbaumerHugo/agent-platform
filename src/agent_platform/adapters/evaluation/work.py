from pydantic import BaseModel, Field

from agent_platform.application.work_orchestrator import WorkOrchestrator
from agent_platform.domain.context import ContextRef
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
    EvaluationResult,
)
from agent_platform.domain.models import RunStatus
from agent_platform.domain.work import (
    WorkRequest,
    WorkStatus,
)


class WorkEvaluationExpected(BaseModel):
    status: WorkStatus
    executed_step_ids: list[str] = Field(default_factory=list)
    run_statuses: list[RunStatus] = Field(default_factory=list)
    failed_step_id: str | None = None
    contexts: list[ContextRef] = Field(default_factory=list)


class WorkEvaluator:
    name = "work_orchestration"

    def __init__(
        self,
        orchestrator: WorkOrchestrator,
    ) -> None:
        self._orchestrator = orchestrator

    async def evaluate(
        self,
        case: EvaluationCase,
    ) -> EvaluationResult:
        request = WorkRequest.model_validate(case.input)
        expected = WorkEvaluationExpected.model_validate(
            case.expected,
        )

        result = await self._orchestrator.execute(request)

        actual_step_ids = [step_result.step_id for step_result in result.step_results]
        actual_run_statuses = [step_result.run.status for step_result in result.step_results]

        status_match = result.status is expected.status
        step_order_match = actual_step_ids == expected.executed_step_ids
        run_statuses_match = actual_run_statuses == expected.run_statuses
        failed_step_match = result.failed_step_id == expected.failed_step_id
        contexts_match = result.contexts == expected.contexts

        expectations_met = all(
            (
                status_match,
                step_order_match,
                run_statuses_match,
                failed_step_match,
                contexts_match,
            )
        )

        return EvaluationResult(
            case_id=case.case_id,
            evaluator=self.name,
            outcome=(EvaluationOutcome.PASS if expectations_met else EvaluationOutcome.FAIL),
            reason_code=("expectations_met" if expectations_met else "expectation_mismatch"),
            metrics={
                "status_match": float(status_match),
                "step_order_match": float(step_order_match),
                "run_statuses_match": float(run_statuses_match),
                "failed_step_match": float(failed_step_match),
                "contexts_match": float(contexts_match),
                "executed_step_count": float(len(actual_step_ids)),
            },
            metadata={
                "actual_status": result.status.value,
                "expected_status": expected.status.value,
                "actual_step_ids": actual_step_ids,
                "actual_run_statuses": [status.value for status in actual_run_statuses],
                "actual_failed_step_id": (result.failed_step_id),
                "actual_contexts": [context.model_dump(mode="json") for context in result.contexts],
            },
        )
