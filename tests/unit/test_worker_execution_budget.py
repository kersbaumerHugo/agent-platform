"""Tests for ModelCallBudget implementation."""

import inspect

import pytest

from agent_platform.worker.execution_budget import (
    ModelCallBudget,
    ModelCallBudgetExceededError,
)


class TestModelCallBudgetInitialization:
    """Tests for ModelCallBudget initialization."""

    def test_max_calls_zero_raises_value_error(self):
        """max_calls=0 should raise ValueError."""
        with pytest.raises(ValueError, match="max_calls must be greater than 0"):
            ModelCallBudget(0)

    def test_negative_max_calls_raises_value_error(self):
        """Negative max_calls should raise ValueError."""
        with pytest.raises(ValueError, match="max_calls must be greater than 0"):
            ModelCallBudget(-1)

    def test_initial_state(self):
        """Initial state for ModelCallBudget(3)."""
        budget = ModelCallBudget(3)
        assert budget.max_calls == 3
        assert budget.consumed_calls == 0
        assert budget.remaining_calls == 3
        assert budget.exhausted is False


class TestModelCallBudgetConsume:
    """Tests for ModelCallBudget.consume() behavior."""

    def test_consume_increments_consumed_calls(self):
        """Each consume() increments consumed_calls by exactly one."""
        budget = ModelCallBudget(5)
        budget.consume()
        assert budget.consumed_calls == 1

    def test_consume_decrements_remaining_calls(self):
        """Each consume() decrements remaining_calls by exactly one."""
        budget = ModelCallBudget(5)
        budget.consume()
        assert budget.remaining_calls == 4

    def test_exhausted_after_max_calls(self):
        """exhausted becomes True after exactly max_calls successful consumes."""
        budget = ModelCallBudget(3)
        budget.consume()
        budget.consume()
        budget.consume()
        assert budget.exhausted is True

    def test_first_consume_after_exhaustion_raises_error(self):
        """First consume() after exhaustion raises ModelCallBudgetExceededError."""
        budget = ModelCallBudget(2)
        budget.consume()
        budget.consume()
        with pytest.raises(ModelCallBudgetExceededError):
            budget.consume()

    def test_rejected_consume_does_not_mutate_state(self):
        """Rejected consumes continue raising and do not mutate state."""
        budget = ModelCallBudget(2)
        budget.consume()
        budget.consume()
        # Try to consume again (should fail)
        with pytest.raises(ModelCallBudgetExceededError):
            budget.consume()

        # State should not have changed
        assert budget.consumed_calls == 2
        assert budget.remaining_calls == 0
        assert budget.exhausted is True

    def test_remaining_calls_never_negative(self):
        """remaining_calls never becomes negative."""
        budget = ModelCallBudget(3)
        for _ in range(3):
            budget.consume()
        assert budget.remaining_calls == 0

        # Even after failed consume, remaining_calls should not be negative
        try:
            budget.consume()
        except ModelCallBudgetExceededError:
            pass
        assert budget.remaining_calls == 0


class TestModelCallBudgetBoundary:
    """Tests for boundary conditions."""

    def test_max_calls_one_boundary(self):
        """max_calls=1 boundary works correctly."""
        budget = ModelCallBudget(1)
        assert budget.max_calls == 1
        assert budget.consumed_calls == 0
        assert budget.remaining_calls == 1
        assert budget.exhausted is False

        budget.consume()
        assert budget.consumed_calls == 1
        assert budget.remaining_calls == 0
        assert budget.exhausted is True

        with pytest.raises(ModelCallBudgetExceededError):
            budget.consume()


class TestModelCallBudgetPropertyDescriptors:
    """Tests for property descriptor behavior."""

    def test_max_calls_is_property_descriptor(self):
        """max_calls is a property descriptor with no setter."""
        budget = ModelCallBudget(5)
        assert isinstance(type(budget).max_calls, property)

        # Verify no setter by checking the property object
        prop = type(budget).max_calls
        assert prop.fset is None

    def test_consumed_calls_is_property_descriptor(self):
        """consumed_calls is a property descriptor with no setter."""
        budget = ModelCallBudget(5)
        assert isinstance(type(budget).consumed_calls, property)
        prop = type(budget).consumed_calls
        assert prop.fset is None

    def test_remaining_calls_is_property_descriptor(self):
        """remaining_calls is a property descriptor with no setter."""
        budget = ModelCallBudget(5)
        assert isinstance(type(budget).remaining_calls, property)
        prop = type(budget).remaining_calls
        assert prop.fset is None

    def test_exhausted_is_property_descriptor(self):
        """exhausted is a property descriptor with no setter."""
        budget = ModelCallBudget(5)
        assert isinstance(type(budget).exhausted, property)
        prop = type(budget).exhausted
        assert prop.fset is None

    def test_assigning_to_max_calls_raises_attribute_error(self):
        """Assigning to max_calls raises AttributeError."""
        budget = ModelCallBudget(5)
        with pytest.raises(AttributeError):
            budget.max_calls = 10

    def test_assigning_to_consumed_calls_raises_attribute_error(self):
        """Assigning to consumed_calls raises AttributeError."""
        budget = ModelCallBudget(5)
        with pytest.raises(AttributeError):
            budget.consumed_calls = 5

    def test_assigning_to_remaining_calls_raises_attribute_error(self):
        """Assigning to remaining_calls raises AttributeError."""
        budget = ModelCallBudget(5)
        with pytest.raises(AttributeError):
            budget.remaining_calls = 2

    def test_assigning_to_exhausted_raises_attribute_error(self):
        """Assigning to exhausted raises AttributeError."""
        budget = ModelCallBudget(5)
        with pytest.raises(AttributeError):
            budget.exhausted = True


class TestModelCallBudgetConsumeSignature:
    """Tests for consume() method signature."""

    def test_consume_signature_only_accepts_self(self):
        """inspect.signature(ModelCallBudget.consume) contains only self."""
        signature = inspect.signature(ModelCallBudget.consume)
        # Should only have 'self' parameter
        params = list(signature.parameters.keys())
        assert params == ["self"]

    def test_consume_with_arguments_raises_type_error(self):
        """Calling budget.consume(2) raises TypeError."""
        budget = ModelCallBudget(5)
        with pytest.raises(TypeError):
            budget.consume(2)
