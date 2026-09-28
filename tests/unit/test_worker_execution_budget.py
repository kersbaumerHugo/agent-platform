"""Tests for ModelRequestBudget and ModelRequestBudgetExceededError."""

import pytest

from agent_platform.worker.execution_budget import (
    ModelRequestBudget,
    ModelRequestBudgetExceededError,
)


class TestModelRequestBudgetInit:
    """Tests for ModelRequestBudget initialization."""

    def test_initial_budget_values(self) -> None:
        """Test that initial state is correct."""
        budget = ModelRequestBudget(max_requests=5)

        assert budget.consumed_requests == 0
        assert budget.remaining_requests == 5
        assert budget.exhausted is False

    def test_rejects_non_positive_max_requests(self) -> None:
        """Test that max_requests <= 0 is rejected."""
        with pytest.raises(ValueError, match="max_requests must be greater than 0"):
            ModelRequestBudget(max_requests=0)

        with pytest.raises(ValueError, match="max_requests must be greater than 0"):
            ModelRequestBudget(max_requests=-1)

        with pytest.raises(ValueError, match="max_requests must be greater than 0"):
            ModelRequestBudget(max_requests=-100)


class TestModelRequestBudgetConsume:
    """Tests for ModelRequestBudget.consume()."""

    def test_successful_consume(self) -> None:
        """Test successful consumption increments counters."""
        budget = ModelRequestBudget(max_requests=5)

        budget.consume()
        assert budget.consumed_requests == 1
        assert budget.remaining_requests == 4
        assert budget.exhausted is False

    def test_multiple_successful_consumes(self) -> None:
        """Test multiple successful consumptions."""
        budget = ModelRequestBudget(max_requests=5)

        for _ in range(5):
            budget.consume()

        assert budget.consumed_requests == 5
        assert budget.remaining_requests == 0
        assert budget.exhausted is True

    def test_consume_after_exhaustion_raises(self) -> None:
        """Test that consuming after exhaustion raises ModelRequestBudgetExceededError."""
        budget = ModelRequestBudget(max_requests=5)

        # Exhaust the budget
        for _ in range(5):
            budget.consume()

        # First consume after exhaustion should raise
        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

    def test_repeated_over_budget_consumes_raise(self) -> None:
        """Test that repeated attempts to consume after exhaustion also raise."""
        budget = ModelRequestBudget(max_requests=3)

        # Exhaust the budget
        for _ in range(3):
            budget.consume()

        # Multiple attempts should all raise
        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

        # State should not change
        assert budget.consumed_requests == 3
        assert budget.remaining_requests == 0
        assert budget.exhausted is True

    def test_rejected_consumes_do_not_change_state(self) -> None:
        """Test that rejected consumes (after exhaustion) do not change state."""
        budget = ModelRequestBudget(max_requests=2)

        # Exhaust the budget
        budget.consume()
        budget.consume()

        assert budget.consumed_requests == 2
        assert budget.remaining_requests == 0
        assert budget.exhausted is True

        # Attempt to consume (should fail)
        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

        # State should remain unchanged
        assert budget.consumed_requests == 2
        assert budget.remaining_requests == 0
        assert budget.exhausted is True


class TestModelRequestBudgetExhaustedProperty:
    """Tests for the exhausted property."""

    def test_exhausted_is_true_when_consumed_equals_max(self) -> None:
        """Test that exhausted is True when consumed equals max_requests."""
        budget = ModelRequestBudget(max_requests=3)

        budget.consume()
        assert budget.exhausted is False

        budget.consume()
        assert budget.exhausted is False

        budget.consume()
        assert budget.exhausted is True

    def test_exhausted_is_false_when_remaining_positive(self) -> None:
        """Test that exhausted is False when there are remaining requests."""
        budget = ModelRequestBudget(max_requests=10)

        budget.consume()
        assert budget.exhausted is False

        budget.consume()
        assert budget.exhausted is False

    def test_exhausted_is_false_when_no_consumed(self) -> None:
        """Test that exhausted is False when nothing has been consumed."""
        budget = ModelRequestBudget(max_requests=1)

        assert budget.exhausted is False


class TestModelRequestBudgetRemainingRequests:
    """Tests for the remaining_requests property."""

    def test_remaining_requests_starts_at_max(self) -> None:
        """Test that remaining_requests starts at max_requests."""
        budget = ModelRequestBudget(max_requests=10)

        assert budget.remaining_requests == 10

    def test_remaining_requests_decreases_with_consumes(self) -> None:
        """Test that remaining_requests decreases with each consume."""
        budget = ModelRequestBudget(max_requests=5)

        assert budget.remaining_requests == 5

        budget.consume()
        assert budget.remaining_requests == 4

        budget.consume()
        assert budget.remaining_requests == 3

        budget.consume()
        assert budget.remaining_requests == 2

    def test_remaining_requests_is_zero_when_exhausted(self) -> None:
        """Test that remaining_requests is 0 when budget is exhausted."""
        budget = ModelRequestBudget(max_requests=5)

        for _ in range(5):
            budget.consume()

        assert budget.remaining_requests == 0


class TestModelRequestBudgetInvariant:
    """Tests for invariants of ModelRequestBudget."""

    def test_remaining_plus_consumed_equals_max(self) -> None:
        """Test that remaining_requests + consumed_requests always equals max_requests."""
        budget = ModelRequestBudget(max_requests=10)

        assert budget.remaining_requests + budget.consumed_requests == 10

        budget.consume()
        assert budget.remaining_requests + budget.consumed_requests == 10

        budget.consume()
        assert budget.remaining_requests + budget.consumed_requests == 10

        budget.consume()
        assert budget.remaining_requests + budget.consumed_requests == 10

    def test_remaining_never_negative(self) -> None:
        """Test that remaining_requests never goes negative."""
        budget = ModelRequestBudget(max_requests=5)

        for _ in range(5):
            budget.consume()

        assert budget.remaining_requests >= 0

        # Attempting to consume beyond exhaustion should not change state
        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

        assert budget.remaining_requests == 0

    def test_consumed_never_exceeds_max(self) -> None:
        """Test that consumed_requests never exceeds max_requests."""
        budget = ModelRequestBudget(max_requests=5)

        for _ in range(5):
            budget.consume()

        assert budget.consumed_requests <= 5

        # Attempting to consume beyond exhaustion should not change state
        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

        assert budget.consumed_requests == 5


class TestModelRequestBudgetEdgeCases:
    """Tests for edge cases."""

    def test_max_requests_of_one(self) -> None:
        """Test budget with max_requests=1."""
        budget = ModelRequestBudget(max_requests=1)

        assert budget.consumed_requests == 0
        assert budget.remaining_requests == 1
        assert budget.exhausted is False

        budget.consume()

        assert budget.consumed_requests == 1
        assert budget.remaining_requests == 0
        assert budget.exhausted is True

        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()

    def test_large_max_requests(self) -> None:
        """Test budget with a large max_requests value."""
        budget = ModelRequestBudget(max_requests=1000)

        assert budget.consumed_requests == 0
        assert budget.remaining_requests == 1000
        assert budget.exhausted is False

        budget.consume()

        assert budget.consumed_requests == 1
        assert budget.remaining_requests == 999
        assert budget.exhausted is False

    def test_max_requests_is_readonly(self) -> None:
        """Test that max_requests is effectively read-only (via property behavior)."""
        budget = ModelRequestBudget(max_requests=10)

        # max_requests is set at initialization and should not change
        assert budget.max_requests == 10

        # Note: We don't test assignment since it's a dataclass field,
        # but we verify it remains constant through operations
        budget.consume()
        budget.consume()
        assert budget.max_requests == 10
