from uuid import uuid4

from prometheus_client import generate_latest

from agent_platform.adapters.observability.prometheus import (
    PrometheusObserver,
)
from agent_platform.domain.observability import (
    ObservationComponent,
    ObservationEvent,
    ObservationStatus,
)


def test_prometheus_observer_records_model_gateway_metrics() -> None:
    observer = PrometheusObserver()

    observer.record(
        ObservationEvent(
            run_id=uuid4(),
            component=ObservationComponent.MODEL_GATEWAY,
            event="model.request.succeeded",
            status=ObservationStatus.SUCCEEDED,
            provider="regression-provider",
            model="regression-model",
            duration_seconds=0.25,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
    )

    metrics = generate_latest().decode()

    assert (
        "agent_platform_model_requests_total{"
        'model="regression-model",'
        'provider="regression-provider",'
        'status="succeeded"} 1.0' in metrics
    )
