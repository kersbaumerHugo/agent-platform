from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_platform.domain.context import ContextContribution, ContextRef


class ContextProviderDecision(StrEnum):
    ACCEPT = "accept"
    ABSTAIN = "abstain"


class ContextSourceEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ContextProviderTrace(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    context: ContextRef
    decision: ContextProviderDecision
    reason_code: str = Field(min_length=1)
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    accepted_sources: tuple[ContextSourceEvidence, ...] = ()

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.candidate_count != self.accepted_count + self.rejected_count:
            raise ValueError(
                "ContextProviderTrace candidate_count must equal accepted_count + rejected_count."
            )

        if self.accepted_count != len(self.accepted_sources):
            raise ValueError("ContextProviderTrace accepted_count must match accepted_sources.")

        if self.decision is ContextProviderDecision.ABSTAIN and self.accepted_count:
            raise ValueError("ContextProviderTrace ABSTAIN decisions cannot accept sources.")

        return self


class ContextProviderResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    contribution: ContextContribution
    trace: ContextProviderTrace

    @model_validator(mode="after")
    def validate_trace_matches_contribution(self) -> Self:
        if self.trace.provider != self.contribution.provider:
            raise ValueError(
                "ContextProviderResult trace provider must match contribution provider."
            )

        if self.trace.context != self.contribution.context:
            raise ValueError("ContextProviderResult trace context must match contribution context.")

        if self.trace.accepted_count != len(self.contribution.items):
            raise ValueError("ContextProviderResult accepted_count must match contribution items.")

        expected_sources = tuple(
            ContextSourceEvidence(
                source_id=item.provenance.source_id,
                content_hash=item.provenance.content_hash,
            )
            for item in self.contribution.items
        )
        if self.trace.accepted_sources != expected_sources:
            raise ValueError(
                "ContextProviderResult accepted_sources must match contribution provenance."
            )

        return self


class ContextBudgetTrace(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_version: str = Field(min_length=1)
    estimator_version: str = Field(min_length=1)
    budget_tokens: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    dropped_item_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_within_budget(self) -> Self:
        if self.estimated_tokens > self.budget_tokens:
            raise ValueError("ContextBudgetTrace estimated_tokens must not exceed budget_tokens.")
        return self


class ContextRenderingTrace(BaseModel):
    model_config = ConfigDict(frozen=True)

    renderer: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ContextInjectionTrace(BaseModel):
    model_config = ConfigDict(frozen=True)

    injector: str = Field(min_length=1)
    version: str = Field(min_length=1)


class ContextPreparationTrace(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str = Field(min_length=1)
    planner: str = Field(min_length=1)
    planner_version: str = Field(min_length=1)
    provider_traces: tuple[ContextProviderTrace, ...] = ()
    assembler_version: str = Field(min_length=1)
    budget: ContextBudgetTrace
    rendering: ContextRenderingTrace
    injection: ContextInjectionTrace
