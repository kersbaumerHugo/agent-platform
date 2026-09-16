from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_platform.domain.context import ContextBundle


class ContextBudget(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_total_tokens: int = Field(gt=0)
    base_input_tokens: int = Field(default=0, ge=0)
    reserved_output_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_reserved_capacity(self) -> Self:
        committed = self.base_input_tokens + self.reserved_output_tokens
        if committed > self.max_total_tokens:
            raise ValueError(
                "base_input_tokens + reserved_output_tokens must not exceed max_total_tokens."
            )
        return self

    @property
    def available_context_tokens(self) -> int:
        return self.max_total_tokens - self.base_input_tokens - self.reserved_output_tokens


class BudgetedContextBundle(BaseModel):
    model_config = ConfigDict(frozen=True)

    bundle: ContextBundle
    budget_tokens: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    dropped_item_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_within_budget(self) -> Self:
        if self.estimated_tokens > self.budget_tokens:
            raise ValueError("estimated_tokens must not exceed budget_tokens.")
        return self
