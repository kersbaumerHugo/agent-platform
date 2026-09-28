"""Budget tracking for model API calls."""

from __future__ import annotations


class ModelCallBudgetExceededError(Exception):
    """Raised when the model call budget is exceeded."""

    def __init__(
        self,
        message: str | None = None,
        *,
        remaining_calls: int = 0,
    ) -> None:
        super().__init__(message or "Model call budget exceeded.")
        self.remaining_calls = remaining_calls


class ModelCallBudget:
    """Tracks and enforces a budget for model API calls."""

    def __init__(self, max_calls: int) -> None:
        """Initialize the budget with a maximum call count.

        Args:
            max_calls: Maximum number of allowed calls.

        Raises:
            ValueError: If max_calls is not positive.
        """
        if max_calls <= 0:
            raise ValueError("max_calls must be greater than 0")

        self._max_calls: int = max_calls
        self._consumed_calls: int = 0

    @property
    def max_calls(self) -> int:
        """Return the maximum allowed calls (read-only)."""
        return self._max_calls

    @property
    def consumed_calls(self) -> int:
        """Return the number of calls consumed (read-only)."""
        return self._consumed_calls

    @property
    def remaining_calls(self) -> int:
        """Return the number of remaining calls (read-only)."""
        return self._max_calls - self._consumed_calls

    @property
    def exhausted(self) -> bool:
        """Return True if the budget is exhausted (read-only)."""
        return self._consumed_calls >= self._max_calls

    def consume(self) -> None:
        """Consume one call from the budget.

        Increments the consumed count if budget is not exhausted.
        Raises ModelCallBudgetExceededError if budget is exhausted.
        """
        if self.exhausted:
            raise ModelCallBudgetExceededError(
                remaining_calls=self.remaining_calls,
            )

        self._consumed_calls += 1
