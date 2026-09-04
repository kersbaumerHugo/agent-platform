from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    input: str = Field(min_length=1)


class RuntimeRequest(BaseModel):
    run_id: UUID
    agent_id: str
    input: str


class RuntimeResult(BaseModel):
    output: str


class RunResult(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    agent_id: str
    status: RunStatus
    output: str | None = None
    error: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
