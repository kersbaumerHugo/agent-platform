"""Model request budget management."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelRequestBudgetExceededError(ValueError):
    """Raised when a model request exceeds its allocated budget."""

    def __init__(
        self,
        *,
        budget: int,
        used: int,
        request_id: str | None = None,
        message: str | None = None,
    ) -> None:
        super().__init__(
            message or f"Model request budget exceeded: {used} tokens used, {budget} tokens budget."
        )
        self.budget = budget
        self.used = used
        self.request_id = request_id


class ModelRequestBudget(BaseModel):
    """Budget for model requests.

    This model tracks token usage against a budget for model requests,
    following the same patterns as ContextBudget.
    """

    model_config = ConfigDict(frozen=True)

    max_total_tokens: int = Field(gt=0, description="Maximum total tokens allowed")
    base_input_tokens: int = Field(default=0, ge=0, description="Base input tokens")
    reserved_output_tokens: int = Field(default=0, ge=0, description="Reserved output tokens")

    @model_validator(mode="after")
    def validate_reserved_capacity(self) -> "ModelRequestBudget":
        committed = self.base_input_tokens + self.reserved_output_tokens
        if committed > self.max_total_tokens:
            raise ValueError(
                "base_input_tokens + reserved_output_tokens must not exceed max_total_tokens."
            )
        return self

    @property
    def available_model_tokens(self) -> int:
        """Return available tokens for model usage."""
        return self.max_total_tokens - self.base_input_tokens - self.reserved_output_tokens

    @property
    def remaining_tokens(self) -> int:
        """Return remaining tokens after accounting for current usage.

        Note: This returns the total available tokens, not accounting for
        any currently used tokens. The used tokens would need to be tracked
        separately if needed for this implementation.
        """
        return self.available_model_tokens
