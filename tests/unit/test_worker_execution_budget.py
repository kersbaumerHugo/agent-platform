"""Unit tests for ModelRequestBudget primitive."""

import pytest

from agent_platform.domain.model_request_budget import ModelRequestBudgetExceededError
from agent_platform.worker.execution_budget import ModelRequestBudget


class TestModelRequestBudget:
    """Test cases for ModelRequestBudget."""

    def test_constructor_rejects_zero(self):
        """Test that constructor rejects max_requests = 0."""
        with pytest.raises(ValueError, match="max_requests must be greater than 0"):
            ModelRequestBudget(max_requests=0)

    def test_constructor_rejects_negative(self):
        """Test that constructor rejects negative max_requests."""
        with pytest.raises(ValueError, match="max_requests must be greater than 0"):
            ModelRequestBudget(max_requests=-5)

    def test_constructor_accepts_positive(self):
        """Test that constructor accepts positive max_requests."""
        budget = ModelRequestBudget(max_requests=10)
        assert budget.max_requests == 10

    def test_initial_consumed_requests_is_zero(self):
        """Test that consumed_requests starts at 0."""
        budget = ModelRequestBudget(max_requests=10)
        assert budget.consumed_requests == 0

    def test_initial_remaining_requests_equals_max(self):
        """Test that remaining_requests equals max_requests initially."""
        budget = ModelRequestBudget(max_requests=10)
        assert budget.remaining_requests == 10

    def test_initial_exhausted_is_false(self):
        """Test that exhausted is False initially."""
        budget = ModelRequestBudget(max_requests=10)
        assert budget.exhausted is False

    def test_consume_increments_consumed_count(self):
        """Test that consume() increments consumed_requests."""
        budget = ModelRequestBudget(max_requests=3)
        assert budget.consume() is True
        assert budget.consumed_requests == 1

    def test_consume_decrements_remaining(self):
        """Test that consume() decreases remaining_requests."""
        budget = ModelRequestBudget(max_requests=5)
        budget.consume()
        assert budget.remaining_requests == 4

    def test_consume_exhausts_budget(self):
        """Test that budget becomes exhausted after consuming max_requests."""
        budget = ModelRequestBudget(max_requests=2)
        budget.consume()
        budget.consume()
        assert budget.exhausted is True
        assert budget.remaining_requests == 0

    def test_consume_fails_when_exhausted(self):
        """Test that consume() raises error when budget is exhausted."""
        budget = ModelRequestBudget(max_requests=2)
        budget.consume()
        budget.consume()
        with pytest.raises(ModelRequestBudgetExceededError, match="exceeded"):
            budget.consume()

    def test_consume_fails_without_incrementing_count(self):
        """Test that failed consume() doesn't increment consumed count."""
        budget = ModelRequestBudget(max_requests=1)
        budget.consume()  # First consume succeeds
        assert budget.consumed_requests == 1
        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()
        # After failed consume, count should still be 1
        assert budget.consumed_requests == 1

    def test_remaining_requests_calculation(self):
        """Test that remaining_requests is correctly calculated."""
        budget = ModelRequestBudget(max_requests=100)
        assert budget.remaining_requests == 100

        budget.consume()
        assert budget.remaining_requests == 99

        budget.consume()
        budget.consume()
        assert budget.remaining_requests == 97

    def test_exhausted_property_with_zero_remaining(self):
        """Test that exhausted is True when remaining is 0."""
        budget = ModelRequestBudget(max_requests=1)
        budget.consume()
        assert budget.exhausted is True
        assert budget.remaining_requests == 0

    def test_exhausted_property_with_positive_remaining(self):
        """Test that exhausted is False when remaining is > 0."""
        budget = ModelRequestBudget(max_requests=5)
        budget.consume()
        assert budget.exhausted is False
        assert budget.remaining_requests == 4

    def test_multiple_consumes_success(self):
        """Test multiple successful consumes."""
        budget = ModelRequestBudget(max_requests=5)
        for i in range(5):
            result = budget.consume()
            assert result is True
            assert budget.consumed_requests == i + 1

        # After 5 consumes, should be exhausted
        assert budget.exhausted is True

    def test_consume_with_large_budget(self):
        """Test with a large budget value."""
        budget = ModelRequestBudget(max_requests=1000)
        assert budget.consume() is True
        assert budget.consumed_requests == 1
        assert budget.remaining_requests == 999

    def test_consume_with_small_budget(self):
        """Test with a small budget value (1)."""
        budget = ModelRequestBudget(max_requests=1)
        assert budget.consume() is True
        assert budget.exhausted is True
        with pytest.raises(ModelRequestBudgetExceededError):
            budget.consume()
