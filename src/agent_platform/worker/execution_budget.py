"""Budget management for model requests."""

from dataclasses import dataclass, field


class ModelRequestBudgetExceededError(Exception):
    """Raised when a model request budget has been exhausted."""

    pass


@dataclass
class ModelRequestBudget:
    """A budget that tracks the number of model requests allowed.

    Attributes:
        max_requests: Maximum number of requests allowed (read-only).
        consumed_requests: Number of requests consumed (read-only).
        remaining_requests: Number of requests remaining (read-only).
        exhausted: Whether the budget has been exhausted (read-only).
    """

    max_requests: int = field(default=0, init=True)
    _consumed_requests: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        """Validate the budget after initialization."""
        if self.max_requests <= 0:
            raise ValueError("max_requests must be greater than 0")

    @property
    def consumed_requests(self) -> int:
        """Get the number of requests consumed."""
        return self._consumed_requests

    @property
    def remaining_requests(self) -> int:
        """Get the number of remaining requests."""
        return self.max_requests - self._consumed_requests

    @property
    def exhausted(self) -> bool:
        """Check if the budget is exhausted."""
        return self._consumed_requests == self.max_requests

    def consume(self) -> None:
        """Consume one request from the budget.

        Raises:
            ModelRequestBudgetExceededError: If the budget is already exhausted.
        """
        if self.exhausted:
            raise ModelRequestBudgetExceededError(
                f"Budget exhausted: consumed {self._consumed_requests}/{self.max_requests} requests"
            )

        self._consumed_requests += 1
