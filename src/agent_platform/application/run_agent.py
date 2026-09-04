from time import perf_counter

from agent_platform.contracts.observability import ObservationContract
from agent_platform.contracts.runtime import RuntimeContract
from agent_platform.domain.models import (
    RunRequest,
    RunResult,
    RunStatus,
    RuntimeRequest,
    utcnow,
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
        self.observer.run_started(run.run_id, self.runtime.name)

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

            self.observer.run_succeeded(
                run.run_id,
                self.runtime.name,
                perf_counter() - started,
            )
            return run

        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error = str(exc)
            run.finished_at = utcnow()

            self.observer.run_failed(
                run.run_id,
                self.runtime.name,
                perf_counter() - started,
            )
            return run
