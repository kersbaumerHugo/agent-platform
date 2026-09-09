from time import perf_counter

from opentelemetry import trace
from opentelemetry.trace import (
    Status,
    StatusCode,
    Tracer,
)

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
        tracer: Tracer | None = None,
    ) -> None:
        self.runtime = runtime
        self.observer = observer
        self._tracer = tracer or trace.get_tracer("agent_platform.run")

    async def execute(self, request: RunRequest) -> RunResult:
        run = RunResult(
            agent_id=request.agent_id,
            status=RunStatus.RUNNING,
        )

        started = perf_counter()

        with self._tracer.start_as_current_span("agent.run") as span:
            span.set_attribute(
                "agent_platform.run.id",
                str(run.run_id),
            )
            span.set_attribute(
                "agent_platform.agent.id",
                request.agent_id,
            )
            span.set_attribute(
                "agent_platform.runtime.name",
                self.runtime.name,
            )

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
                with self._tracer.start_as_current_span("runtime.execute") as runtime_span:
                    runtime_span.set_attribute(
                        "agent_platform.run.id",
                        str(run.run_id),
                    )
                    runtime_span.set_attribute(
                        "agent_platform.runtime.name",
                        self.runtime.name,
                    )

                    runtime_result = await self.runtime.execute(
                        RuntimeRequest(
                            run_id=run.run_id,
                            agent_id=request.agent_id,
                            input=request.input,
                        )
                    )

                    runtime_span.set_status(Status(StatusCode.OK))

                run.status = RunStatus.SUCCEEDED
                run.output = runtime_result.output
                run.finished_at = utcnow()

                duration = perf_counter() - started

                span.set_attribute(
                    "agent_platform.run.status",
                    "succeeded",
                )
                span.set_status(Status(StatusCode.OK))

                self.observer.record(
                    ObservationEvent(
                        run_id=run.run_id,
                        component=ObservationComponent.RUN,
                        event="run.succeeded",
                        status=ObservationStatus.SUCCEEDED,
                        runtime=self.runtime.name,
                        duration_seconds=duration,
                    )
                )

                return run

            except Exception as exc:
                run.status = RunStatus.FAILED
                run.error = str(exc)
                run.finished_at = utcnow()

                duration = perf_counter() - started

                span.set_attribute(
                    "agent_platform.run.status",
                    "failed",
                )
                span.set_attribute(
                    "error.type",
                    type(exc).__name__,
                )
                span.record_exception(exc)
                span.set_status(
                    Status(
                        StatusCode.ERROR,
                        type(exc).__name__,
                    )
                )

                self.observer.record(
                    ObservationEvent(
                        run_id=run.run_id,
                        component=ObservationComponent.RUN,
                        event="run.failed",
                        status=ObservationStatus.FAILED,
                        runtime=self.runtime.name,
                        duration_seconds=duration,
                        error_type=type(exc).__name__,
                    )
                )

                return run
