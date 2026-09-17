from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_platform.domain.context import ContextRef
from agent_platform.domain.context_rendering import RenderedContext
from agent_platform.domain.context_trace import ContextPreparationTrace


class RecallIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    objective: str = Field(min_length=1)
    step_input: str = Field(min_length=1)
    contexts: tuple[ContextRef, ...] = ()

    @model_validator(mode="after")
    def validate_unique_contexts(self) -> Self:
        context_keys = [(context.role, context.namespace) for context in self.contexts]

        if len(context_keys) != len(set(context_keys)):
            raise ValueError("RecallIntent contexts must be unique by role and namespace.")

        return self


class RecallRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(min_length=1)
    context: ContextRef
    query: str = Field(min_length=1)
    limit: int = Field(default=5, gt=0)


class RecallPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    planner: str = Field(min_length=1)
    version: str = Field(min_length=1)
    requests: tuple[RecallRequest, ...] = ()

    @model_validator(mode="after")
    def validate_unique_request_ids(self) -> Self:
        request_ids = [request.request_id for request in self.requests]

        if len(request_ids) != len(set(request_ids)):
            raise ValueError("RecallPlan request_id values must be unique.")

        return self


class ContextPreparationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    rendered: RenderedContext
    trace: ContextPreparationTrace

    @model_validator(mode="after")
    def validate_trace_matches_rendered_context(self) -> Self:
        rendering = self.trace.rendering

        if (
            rendering.renderer != self.rendered.renderer
            or rendering.version != self.rendered.version
            or rendering.content_hash != self.rendered.content_hash
        ):
            raise ValueError(
                "ContextPreparationResult trace rendering must match rendered context."
            )

        return self
