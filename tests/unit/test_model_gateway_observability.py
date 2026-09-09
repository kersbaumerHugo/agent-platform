from uuid import uuid4

import pytest

from agent_platform.application.model_gateway import ModelGateway
from agent_platform.domain.model import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelResult,
    TokenUsage,
)
from agent_platform.domain.observability import (
    ObservationEvent,
    ObservationStatus,
)


class FakeModel:
    provider = "fake-provider"
    model = "fake-route"

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        return ModelResult(
            provider=self.provider,
            model="resolved-fake-model",
            output="observed",
            usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
        )


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def record(self, event: ObservationEvent) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_model_gateway_emits_correlated_events() -> None:
    observer = RecordingObserver()
    run_id = uuid4()

    gateway = ModelGateway(
        FakeModel(),
        observer,
    )

    result = await gateway.generate(
        ModelRequest(
            run_id=run_id,
            messages=[
                ModelMessage(
                    role=MessageRole.USER,
                    content="observe me",
                )
            ],
        )
    )

    assert result.output == "observed"
    assert len(observer.events) == 2

    started, succeeded = observer.events

    assert started.run_id == run_id
    assert succeeded.run_id == run_id

    assert started.status == ObservationStatus.STARTED
    assert succeeded.status == ObservationStatus.SUCCEEDED

    assert succeeded.provider == "fake-provider"
    assert succeeded.model == "fake-route"
    assert succeeded.resolved_model == ("resolved-fake-model")

    assert succeeded.total_tokens == 15
    assert succeeded.duration_seconds is not None
