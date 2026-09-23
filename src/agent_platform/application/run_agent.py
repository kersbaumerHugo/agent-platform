import re
from time import perf_counter

from opentelemetry import trace
from opentelemetry.trace import (
    Status,
    StatusCode,
    Tracer,
)

from agent_platform.application.run_context import (
    InMemoryRunContextBindings,
)
from agent_platform.contracts.observability import (
    ObservationContract,
)
from agent_platform.contracts.run_history import (
    RunHistoryStoreContract,
)
from agent_platform.contracts.runtime import RuntimeContract
from agent_platform.domain.context_preparation import (
    ContextPreparationResult,
)
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
from agent_platform.domain.run_history import (
    RunHistoryCompletion,
    RunHistoryStart,
)

_FULL_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class RunAgent:
    def __init__(
        self,
        runtime: RuntimeContract,
        observer: ObservationContract,
        tracer: Tracer | None = None,
        run_context_bindings: InMemoryRunContextBindings | None = None,
        run_history_store: RunHistoryStoreContract | None = None,
        platform_revision: str | None = None,
        repository_revision: str | None = None,
    ) -> None:
        self.runtime = runtime
        self.observer = observer
        self._tracer = tracer or trace.get_tracer("agent_platform.run")
        self._run_context_bindings = run_context_bindings
        self._run_history_store = run_history_store

        if run_history_store is None:
            if platform_revision is not None or repository_revision is not None:
                raise ValueError("Run history revisions require a configured run history store.")

            self._platform_revision = None
            self._repository_revision = None
            return

        self._platform_revision = _require_full_git_sha(
            platform_revision,
            "platform_revision",
        )

        if repository_revision is None:
            self._repository_revision = None
        else:
            self._repository_revision = _require_full_git_sha(
                repository_revision,
                "repository_revision",
            )

    async def execute(
        self,
        request: RunRequest,
        *,
        prepared_context: ContextPreparationResult | None = None,
    ) -> RunResult:
        run = RunResult(
            agent_id=request.agent_id,
            status=RunStatus.RUNNING,
        )

        started = perf_counter()
        context_bound = False

        if self._run_history_store is not None:
            assert self._platform_revision is not None

            self._run_history_store.start_run(
                RunHistoryStart(
                    run_id=run.run_id,
                    agent_id=request.agent_id,
                    platform_revision=self._platform_revision,
                    repository_revision=self._repository_revision,
                    runtime=self.runtime.name,
                    input=request.input,
                    started_at=run.started_at,
                )
            )

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
                if prepared_context is not None:
                    if self._run_context_bindings is None:
                        raise RuntimeError("Prepared context requires run-scoped context bindings.")

                    self._run_context_bindings.require(run.run_id)

                    try:
                        self._run_context_bindings.bind(
                            run.run_id,
                            prepared_context,
                        )
                    except Exception:
                        self._run_context_bindings.release(run.run_id)
                        raise

                    context_bound = True

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
                finally:
                    if context_bound and self._run_context_bindings is not None:
                        self._run_context_bindings.release(run.run_id)

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

        if self._run_history_store is not None:
            assert run.finished_at is not None

            self._run_history_store.finish_run(
                RunHistoryCompletion(
                    run_id=run.run_id,
                    status=run.status,
                    output=run.output,
                    error=run.error,
                    finished_at=run.finished_at,
                    duration_seconds=duration,
                )
            )

        return run


def _require_full_git_sha(
    value: str | None,
    name: str,
) -> str:
    if value is None or not _FULL_GIT_SHA.fullmatch(value):
        raise ValueError(f"{name} must be a full lowercase 40-character Git SHA-1.")

    return value
