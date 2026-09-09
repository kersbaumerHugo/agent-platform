from time import perf_counter

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, Tracer

from agent_platform.contracts.model import ModelContract
from agent_platform.contracts.observability import (
    ObservationContract,
)
from agent_platform.domain.model import (
    ModelRequest,
    ModelResult,
)
from agent_platform.domain.observability import (
    ObservationComponent,
    ObservationEvent,
    ObservationStatus,
)


class ModelGateway:
    def __init__(
        self,
        model: ModelContract,
        observer: ObservationContract,
        tracer: Tracer | None = None,
    ) -> None:
        self._model = model
        self._observer = observer
        self._tracer = tracer or trace.get_tracer("agent_platform.model_gateway")

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        started = perf_counter()

        with self._tracer.start_as_current_span("model.gateway") as span:
            span.set_attribute(
                "agent_platform.run.id",
                str(request.run_id),
            )
            span.set_attribute(
                "gen_ai.provider.name",
                self._model.provider,
            )
            span.set_attribute(
                "gen_ai.request.model",
                self._model.model,
            )

            self._observer.record(
                ObservationEvent(
                    run_id=request.run_id,
                    component=(ObservationComponent.MODEL_GATEWAY),
                    event="model.request.started",
                    status=ObservationStatus.STARTED,
                    provider=self._model.provider,
                    model=self._model.model,
                )
            )

            try:
                result = await self._model.generate(request)

            except Exception as exc:
                duration = perf_counter() - started

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

                self._observer.record(
                    ObservationEvent(
                        run_id=request.run_id,
                        component=(ObservationComponent.MODEL_GATEWAY),
                        event="model.request.failed",
                        status=ObservationStatus.FAILED,
                        provider=self._model.provider,
                        model=self._model.model,
                        duration_seconds=duration,
                        error_type=type(exc).__name__,
                    )
                )

                raise

            duration = perf_counter() - started
            usage = result.usage

            span.set_attribute(
                "gen_ai.response.model",
                result.model,
            )
            span.set_attribute(
                "agent_platform.model.status",
                "succeeded",
            )

            if usage is not None:
                span.set_attribute(
                    "gen_ai.usage.input_tokens",
                    usage.prompt_tokens,
                )
                span.set_attribute(
                    "gen_ai.usage.output_tokens",
                    usage.completion_tokens,
                )

            span.set_status(Status(StatusCode.OK))

            self._observer.record(
                ObservationEvent(
                    run_id=request.run_id,
                    component=(ObservationComponent.MODEL_GATEWAY),
                    event="model.request.succeeded",
                    status=ObservationStatus.SUCCEEDED,
                    provider=self._model.provider,
                    model=self._model.model,
                    resolved_model=result.model,
                    duration_seconds=duration,
                    prompt_tokens=(usage.prompt_tokens if usage is not None else None),
                    completion_tokens=(usage.completion_tokens if usage is not None else None),
                    total_tokens=(usage.total_tokens if usage is not None else None),
                )
            )

            return result
