from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from agent_platform.domain.models import RunStatus
from agent_platform.domain.observability import ObservationStatus

GitRevision = Annotated[
    str,
    StringConstraints(
        pattern=r"^[0-9a-f]{40}$",
    ),
]


class RunHistoryStart(BaseModel):
    """Immutable identity and starting state for one platform run."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    run_id: UUID
    agent_id: str = Field(min_length=1)

    platform_revision: GitRevision
    repository_revision: GitRevision | None = None

    runtime: str = Field(min_length=1)
    input: str = Field(min_length=1)
    started_at: datetime


class RunHistoryCompletion(BaseModel):
    """Terminal state for one platform run."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    run_id: UUID
    status: RunStatus

    output: str | None = None
    error: str | None = None

    finished_at: datetime
    duration_seconds: float = Field(ge=0)


class RunHistoryRecord(BaseModel):
    """Persisted run evidence reconstructed from the history store."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    run_id: UUID
    agent_id: str = Field(min_length=1)

    platform_revision: GitRevision
    repository_revision: GitRevision | None = None

    runtime: str = Field(min_length=1)
    input: str = Field(min_length=1)

    status: RunStatus
    output: str | None = None
    error: str | None = None

    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: float | None = Field(
        default=None,
        ge=0,
    )


class ModelInvocationRecord(BaseModel):
    """One completed model invocation correlated to a platform run."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    run_id: UUID

    provider: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    resolved_model: str | None = None

    status: ObservationStatus
    observed_at: datetime

    duration_seconds: float | None = Field(
        default=None,
        ge=0,
    )

    prompt_tokens: int | None = Field(
        default=None,
        ge=0,
    )
    completion_tokens: int | None = Field(
        default=None,
        ge=0,
    )
    total_tokens: int | None = Field(
        default=None,
        ge=0,
    )

    error_type: str | None = None


class ToolInvocationRecord(BaseModel):
    """One completed tool invocation correlated to a platform run."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    run_id: UUID
    tool_name: str = Field(min_length=1)

    status: ObservationStatus
    observed_at: datetime

    duration_seconds: float | None = Field(
        default=None,
        ge=0,
    )
    error_type: str | None = None
