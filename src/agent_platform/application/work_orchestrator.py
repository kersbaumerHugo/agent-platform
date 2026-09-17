from agent_platform.application.context_preparation import PrepareContext
from agent_platform.application.run_agent import RunAgent
from agent_platform.domain.context_budget import ContextBudget
from agent_platform.domain.context_preparation import (
    ContextPreparationResult,
)
from agent_platform.domain.models import (
    RunRequest,
    RunResult,
    RunStatus,
    utcnow,
)
from agent_platform.domain.work import (
    WorkRequest,
    WorkResult,
    WorkStatus,
    WorkStepResult,
)


class WorkOrchestrator:
    def __init__(
        self,
        run_agent: RunAgent,
        *,
        prepare_context: PrepareContext | None = None,
        context_budget: ContextBudget | None = None,
    ) -> None:
        if (prepare_context is None) != (context_budget is None):
            raise ValueError("prepare_context and context_budget must be configured together.")

        self._run_agent = run_agent
        self._prepare_context = prepare_context
        self._context_budget = context_budget

    async def execute(self, request: WorkRequest) -> WorkResult:
        work = WorkResult(
            status=WorkStatus.RUNNING,
            contexts=list(request.contexts),
        )

        for step in request.steps:
            prepared_context: ContextPreparationResult | None = None

            if request.contexts and self._prepare_context is not None:
                assert self._context_budget is not None

                try:
                    prepared_context = await self._prepare_context.execute(
                        objective=request.objective,
                        step_input=step.input,
                        contexts=request.contexts,
                        budget=self._context_budget,
                    )
                except Exception as exc:
                    run = RunResult(
                        agent_id=step.agent_id,
                        status=RunStatus.FAILED,
                        error=(f"context preparation failed: {type(exc).__name__}: {exc}"),
                        finished_at=utcnow(),
                    )

                    work.step_results.append(
                        WorkStepResult(
                            step_id=step.step_id,
                            run=run,
                        )
                    )
                    work.status = WorkStatus.FAILED
                    work.failed_step_id = step.step_id
                    work.finished_at = utcnow()
                    return work

            run = await self._run_agent.execute(
                RunRequest(
                    agent_id=step.agent_id,
                    input=step.input,
                ),
                prepared_context=prepared_context,
            )

            work.step_results.append(
                WorkStepResult(
                    step_id=step.step_id,
                    run=run,
                    context_trace=(
                        prepared_context.trace if prepared_context is not None else None
                    ),
                )
            )

            if run.status is RunStatus.FAILED:
                work.status = WorkStatus.FAILED
                work.failed_step_id = step.step_id
                work.finished_at = utcnow()
                return work

        work.status = WorkStatus.SUCCEEDED
        work.finished_at = utcnow()
        return work
