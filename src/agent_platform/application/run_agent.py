from time import perf_counter

from agent_platform.contracts.observability import (
    ObservationContract,
)
from agent_platform.contracts.runtime import RuntimeContract
from agent_platform.domain.models import (
    RunRequest,
    RunResult,
    RunStatus,
    RuntimeRequest,
    utcnow,
)
from agent_platform.domain.observability import (
    ObservationComponent,
    ObservationEvent,
    ObservationStatus,
)


class RunAgent:
    def __init__(
        self,
        runtime: RuntimeContract,
        observer: ObservationContract,
    ) -> None:
        self.runtime = runtime
        self.observer = observer

    async def execute(self, request: RunRequest) -> RunResult:
        run = RunResult(
            agent_id=request.agent_id,
            status=RunStatus.RUNNING,
        )

        started = perf_counter()

        self.observer.record(
            ObservationEvent(
                run_id=run.run_id,
                component=ObservationComponent.RUN,
                event="run.started",
                status=ObservationStatus.STARTED,
                runtime=self.runtime.name,
            )
        )

        try:
            runtime_result = await self.runtime.execute(
                RuntimeRequest(
                    run_id=run.run_id,
                    agent_id=request.agent_id,
                    input=request.input,
                )
            )

            run.status = RunStatus.SUCCEEDED
            run.output = runtime_result.output
            run.finished_at = utcnow()

            self.observer.record(
                ObservationEvent(
                    run_id=run.run_id,
                    component=ObservationComponent.RUN,
                    event="run.succeeded",
                    status=ObservationStatus.SUCCEEDED,
                    runtime=self.runtime.name,
                    duration_seconds=(perf_counter() - started),
                )
            )

            return run

        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error = str(exc)
            run.finished_at = utcnow()

            self.observer.record(
                ObservationEvent(
                    run_id=run.run_id,
                    component=ObservationComponent.RUN,
                    event="run.failed",
                    status=ObservationStatus.FAILED,
                    runtime=self.runtime.name,
                    duration_seconds=(perf_counter() - started),
                    error_type=type(exc).__name__,
                )
            )

            return run
