from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from agent_platform.domain.models import RunResult, utcnow


class ContextRole(StrEnum):
    SHARED = "shared"
    DELIVERY = "delivery"
    SUBJECT = "subject"


class ContextRef(BaseModel):
    role: ContextRole
    namespace: str = Field(min_length=1)


class WorkStep(BaseModel):
    step_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    input: str = Field(min_length=1)


class WorkRequest(BaseModel):
    objective: str = Field(min_length=1)
    contexts: list[ContextRef] = Field(default_factory=list)
    steps: list[WorkStep] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_refs_and_steps(self) -> Self:
        context_keys = [(context.role, context.namespace) for context in self.contexts]

        if len(context_keys) != len(set(context_keys)):
            raise ValueError("WorkRequest contexts must be unique by role and namespace.")

        step_ids = [step.step_id for step in self.steps]

        if len(step_ids) != len(set(step_ids)):
            raise ValueError("WorkRequest step_id values must be unique.")

        return self


class WorkStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WorkStepResult(BaseModel):
    step_id: str = Field(min_length=1)
    run: RunResult


class WorkResult(BaseModel):
    work_id: UUID = Field(default_factory=uuid4)
    status: WorkStatus
    contexts: list[ContextRef] = Field(default_factory=list)
    step_results: list[WorkStepResult] = Field(default_factory=list)
    failed_step_id: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
