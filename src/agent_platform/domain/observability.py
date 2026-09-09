from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class ObservationComponent(StrEnum):
    RUN = "run"
    MODEL_GATEWAY = "model_gateway"


class ObservationStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ObservationEvent(BaseModel):
    run_id: UUID
    component: ObservationComponent
    event: str
    status: ObservationStatus

    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    runtime: str | None = None

    provider: str | None = None
    model: str | None = None
    resolved_model: str | None = None

    duration_seconds: float | None = Field(
        default=None,
        ge=0,
    )

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)

    error_type: str | None = None
