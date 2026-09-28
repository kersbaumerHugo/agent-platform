"""Execution budget tracking for model requests."""

from dataclasses import dataclass


class ModelRequestBudgetExceededError(Exception):
    """Exception raised when model request budget is exceeded."""

    def __init__(
        self,
        message: str,
        consumed_requests: int,
        max_requests: int,
    ) -> None:
        super().__init__(message)
        self.consumed_requests = consumed_requests
        self.max_requests = max_requests


@dataclass
class ModelRequestBudget:
    """Tracks request budget for model requests."""

    max_requests: int
    consumed_requests: int = 0

    def __post_init__(self) -> None:
        """Validate that max_requests is positive."""
        if self.max_requests <= 0:
            raise ValueError("max_requests must be greater than 0")

    @property
    def remaining_requests(self) -> int:
        """Get remaining requests, ensuring non-negative."""
        return max(0, self.max_requests - self.consumed_requests)

    @property
    def exhausted(self) -> bool:
        """Check if budget is exhausted."""
        return self.consumed_requests >= self.max_requests

    def consume(self, requests: int = 1) -> None:
        """
        Consume a request from the budget.

        Args:
            requests: Number of requests to consume (default: 1)

        Raises:
            ModelRequestBudgetExceededError: If budget is exhausted
        """
        if self.consumed_requests + requests > self.max_requests:
            raise ModelRequestBudgetExceededError(
                f"Budget exceeded: consumed {self.consumed_requests} "
                f"requests, max is {self.max_requests}",
                consumed_requests=self.consumed_requests,
                max_requests=self.max_requests,
            )

        self.consumed_requests += requests
