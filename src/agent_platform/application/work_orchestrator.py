from agent_platform.application.run_agent import RunAgent
from agent_platform.domain.models import RunRequest, RunStatus, utcnow
from agent_platform.domain.work import (
    WorkRequest,
    WorkResult,
    WorkStatus,
    WorkStepResult,
)


class WorkOrchestrator:
    def __init__(self, run_agent: RunAgent) -> None:
        self._run_agent = run_agent

    async def execute(self, request: WorkRequest) -> WorkResult:
        work = WorkResult(
            status=WorkStatus.RUNNING,
            contexts=list(request.contexts),
        )

        for step in request.steps:
            run = await self._run_agent.execute(
                RunRequest(
                    agent_id=step.agent_id,
                    input=step.input,
                )
            )

            work.step_results.append(
                WorkStepResult(
                    step_id=step.step_id,
                    run=run,
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
