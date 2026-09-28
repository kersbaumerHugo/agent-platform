"""Tests for execution budget management."""

import pytest

from agent_platform.worker.execution_budget import (
    ModelRequestBudget,
    ModelRequestBudgetExceededError,
)


class TestInvalidMaxRequests:
    """Test invalid max_requests values raise ValueError."""

    def test_max_requests_zero_raises(self) -> None:
        """Test that max_requests=0 raises ValueError."""
        with pytest.raises(ValueError, match="max_requests must be greater than 0"):
            ModelRequestBudget(max_requests=0)

    def test_max_requests_negative_raises(self) -> None:
        """Test that negative max_requests raises ValueError."""
        with pytest.raises(ValueError, match="max_requests must be greater than 0"):
            ModelRequestBudget(max_requests=-1)

    def test_max_requests_float_raises(self) -> None:
        """Test that float max_requests raises ValueError."""
        with pytest.raises(ValueError, match="max_requests must be greater than 0"):
            ModelRequestBudget(max_requests=0.0)


class TestInitialState:
    """Test initial state of ModelRequestBudget."""

    def test_initial_consumed_requests(self) -> None:
        """Test that consumed_requests is 0 initially."""
        budget = ModelRequestBudget(max_requests=10)
        assert budget._consumed_requests == 0

    def test_initial_remaining_requests(self) -> None:
        """Test that remaining_requests equals max_requests initially."""
        budget = ModelRequestBudget(max_requests=10)
        assert budget.remaining_requests == 10

    def test_initial_exhausted(self) -> None:
        """Test that exhausted is False initially."""
        budget = ModelRequestBudget(max_requests=10)
        assert budget.exhausted is False


class TestDeterministicConsumption:
    """Test deterministic consumption behavior."""

    def test_consume_increments_consumed_requests(self) -> None:
        """Test that consume() increments consumed_requests correctly."""
        budget = ModelRequestBudget(max_requests=5)
        budget.consume()
        assert budget._consumed_requests == 1

    def test_remaining_count_decreases(self) -> None:
        """Test that remaining count decreases correctly with each consume()."""
        budget = ModelRequestBudget(max_requests=5)
        budget.consume()
        budget.consume()
        assert budget.remaining_requests == 3


class TestExhaustionBoundary:
    """Test exhaustion boundary conditions."""

    def test_exhausted_after_max_requests(self) -> None:
        """Test that exhausted=True after max_requests consume() calls."""
        budget = ModelRequestBudget(max_requests=5)
        for _ in range(5):
            budget.consume()
        assert budget.exhausted is True

    def test_exhausted_before_max_requests(self) -> None:
        """Test that exhausted=False before max_requests consume() calls."""
        budget = ModelRequestBudget(max_requests=5)
        for _ in range(3):
            budget.consume()
        assert budget.exhausted is False


class TestOverBudgetRejection:
    """Test over-budget rejection behavior."""

    def test_first_over_budget_raises(self) -> None:
        """Test that first over-budget attempt raises ModelRequestBudgetExceededError."""
        budget = ModelRequestBudget(max_requests=3)
        budget.consume()
        budget.consume()
        budget.consume()  # Now exhausted

        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

    def test_repeated_rejection_raises(self) -> None:
        """Test that multiple over-budget attempts all raise exception."""
        budget = ModelRequestBudget(max_requests=2)
        budget.consume()
        budget.consume()  # Exhausted

        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

    def test_no_increment_on_rejection(self) -> None:
        """Test that consumed_requests stays the same after over-budget attempt."""
        budget = ModelRequestBudget(max_requests=2)
        budget.consume()
        budget.consume()  # Exhausted

        initial_consumed = budget._consumed_requests
        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

        assert budget._consumed_requests == initial_consumed

        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

        assert budget._consumed_requests == initial_consumed


class TestMaxRequestsOne:
    """Test with max_requests=1."""

    def test_exhaust_after_one_consume(self) -> None:
        """Test exhaust after one consume() with max_requests=1."""
        budget = ModelRequestBudget(max_requests=1)
        budget.consume()
        assert budget._consumed_requests == 1
        assert budget.exhausted is True
        assert budget.remaining_requests == 0

    def test_raise_on_second_consume(self) -> None:
        """Test raise on second consume() after exhaustion."""
        budget = ModelRequestBudget(max_requests=1)
        budget.consume()

        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

        assert budget._consumed_requests == 1
        assert budget.remaining_requests == 0
