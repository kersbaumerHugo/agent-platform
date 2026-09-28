"""Execution budget management for model requests."""


class ModelRequestBudgetExceededError(Exception):
    """Exception raised when a model request budget is exceeded."""

    def __init__(self, message: str = "Model request budget exceeded.") -> None:
        super().__init__(message)


class ModelRequestBudget:
    """Budget tracker for model requests."""

    def __init__(self, max_requests: int) -> None:
        """Initialize the budget.

        Args:
            max_requests: The maximum number of requests allowed.

        Raises:
            ValueError: If max_requests is not greater than 0.
        """
        if max_requests <= 0:
            raise ValueError("max_requests must be greater than 0")
        self._max_requests = max_requests
        self._consumed_requests: int = 0

    @property
    def remaining_requests(self) -> int:
        """Return the number of remaining requests (never negative)."""
        return max(0, self._max_requests - self._consumed_requests)

    @property
    def exhausted(self) -> bool:
        """Return True if the budget is exhausted."""
        return self._consumed_requests == self._max_requests

    def consume(self) -> bool:
        """Consume a request from the budget.

        Returns:
            True if the request was consumed successfully.

        Raises:
            ModelRequestBudgetExceededError: If the budget is exhausted.
        """
        if self.exhausted:
            raise ModelRequestBudgetExceededError(
                f"Model request budget exceeded. Remaining requests: {self.remaining_requests}"
            )
        self._consumed_requests += 1
        return True
