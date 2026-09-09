from time import perf_counter

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
    ) -> None:
        self._model = model
        self._observer = observer

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        started = perf_counter()

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
            self._observer.record(
                ObservationEvent(
                    run_id=request.run_id,
                    component=(ObservationComponent.MODEL_GATEWAY),
                    event="model.request.failed",
                    status=ObservationStatus.FAILED,
                    provider=self._model.provider,
                    model=self._model.model,
                    duration_seconds=(perf_counter() - started),
                    error_type=type(exc).__name__,
                )
            )

            raise

        usage = result.usage

        self._observer.record(
            ObservationEvent(
                run_id=request.run_id,
                component=(ObservationComponent.MODEL_GATEWAY),
                event="model.request.succeeded",
                status=ObservationStatus.SUCCEEDED,
                provider=self._model.provider,
                model=self._model.model,
                resolved_model=result.model,
                duration_seconds=(perf_counter() - started),
                prompt_tokens=(usage.prompt_tokens if usage is not None else None),
                completion_tokens=(usage.completion_tokens if usage is not None else None),
                total_tokens=(usage.total_tokens if usage is not None else None),
            )
        )

        return result
