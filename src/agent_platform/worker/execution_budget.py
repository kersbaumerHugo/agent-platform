"""Model request budget primitive for tracking and limiting model requests."""

from agent_platform.domain.model_request_budget import ModelRequestBudgetExceededError


class ModelRequestBudget:
    """
    A deterministic primitive for tracking and limiting model requests.

    This class tracks the number of requests consumed and enforces a maximum
    request limit. When the limit is reached, further consume() calls will
    raise ModelRequestBudgetExceededError without incrementing the consumed count.
    """

    def __init__(self, max_requests: int):
        """
        Initialize the model request budget.

        Args:
            max_requests: The maximum number of requests allowed (must be > 0).

        Raises:
            ValueError: If max_requests is <= 0.
        """
        if max_requests <= 0:
            raise ValueError("max_requests must be greater than 0")

        self._max_requests = max_requests
        self._consumed_requests = 0

    @property
    def max_requests(self) -> int:
        """Get the maximum number of requests allowed."""
        return self._max_requests

    @property
    def consumed_requests(self) -> int:
        """Get the number of requests consumed."""
        return self._consumed_requests

    @property
    def remaining_requests(self) -> int:
        """Get the number of remaining requests."""
        return self._max_requests - self._consumed_requests

    @property
    def exhausted(self) -> bool:
        """Check if the budget has been exhausted (no remaining requests)."""
        return self._consumed_requests >= self._max_requests

    def consume(self) -> bool:
        """
        Consume a request from the budget.

        Returns:
            True if the request was successfully consumed.

        Raises:
            ModelRequestBudgetExceededError: If the budget is exhausted.
        """
        if self._consumed_requests >= self._max_requests:
            raise ModelRequestBudgetExceededError(
                f"Model request budget exceeded: consumed {self._consumed_requests} "
                f"out of max {self._max_requests} requests"
            )

        self._consumed_requests += 1
        return True
