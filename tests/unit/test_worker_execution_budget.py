"""Regression tests for ModelCallBudget implementation."""

from __future__ import annotations

import inspect

import pytest

from agent_platform.worker.execution_budget import ModelCallBudget, ModelCallBudgetExceededError


class TestModelCallBudgetValidation:
    """Test that invalid initializations raise ValueError."""

    def test_zero_max_calls_raises(self) -> None:
        """Zero max_calls should raise ValueError."""
        with pytest.raises(ValueError, match="max_calls must be greater than 0"):
            ModelCallBudget(0)

    def test_negative_max_calls_raises(self) -> None:
        """Negative max_calls should raise ValueError."""
        with pytest.raises(ValueError, match="max_calls must be greater than 0"):
            ModelCallBudget(-1)

    def test_max_calls_one_is_valid(self) -> None:
        """One max_calls should be valid."""
        budget = ModelCallBudget(1)
        assert budget is not None


class TestModelCallBudgetInitialState:
    """Test initial public state for ModelCallBudget(3)."""

    def test_initial_state(self) -> None:
        """Initial state for budget with max_calls=3."""
        budget = ModelCallBudget(3)
        assert budget.max_calls == 3
        assert budget.consumed_calls == 0
        assert budget.remaining_calls == 3
        assert budget.exhausted is False


class TestModelCallBudgetConsume:
    """Test consume() functionality."""

    def test_consume_increments_consumed_and_decrements_remaining(self) -> None:
        """consume() increments consumed_calls by 1 and decrements remaining_calls by 1."""
        budget = ModelCallBudget(5)

        budget.consume()
        assert budget.consumed_calls == 1
        assert budget.remaining_calls == 4

        budget.consume()
        assert budget.consumed_calls == 2
        assert budget.remaining_calls == 3


class TestModelCallBudgetExhaustion:
    """Test exhaustion behavior."""

    def test_exhausted_becomes_true_after_max_calls(self) -> None:
        """exhausted becomes true exactly after max_calls successful calls."""
        budget = ModelCallBudget(3)

        budget.consume()
        assert budget.exhausted is False

        budget.consume()
        assert budget.exhausted is False

        budget.consume()
        assert budget.exhausted is True

    def test_first_consume_after_exhaustion_raises(self) -> None:
        """First consume after exhaustion raises ModelCallBudgetExceededError."""
        budget = ModelCallBudget(2)
        budget.consume()
        budget.consume()
        assert budget.exhausted is True

        with pytest.raises(ModelCallBudgetExceededError):
            budget.consume()

    def test_multiple_consume_after_exhaustion_raises(self) -> None:
        """Perform at least three consecutive consume() attempts after exhaustion.
        Each attempt must raise ModelCallBudgetExceededError and after each attempt
        assert max_calls, consumed_calls, remaining_calls and exhausted are unchanged."""
        budget = ModelCallBudget(1)
        budget.consume()
        assert budget.exhausted is True
        initial_max_calls = budget.max_calls
        initial_consumed_calls = budget.consumed_calls
        initial_remaining_calls = budget.remaining_calls

        # First additional consume attempt
        with pytest.raises(ModelCallBudgetExceededError):
            budget.consume()
        assert budget.max_calls == initial_max_calls
        assert budget.consumed_calls == initial_consumed_calls
        assert budget.remaining_calls == initial_remaining_calls
        assert budget.exhausted is True

        # Second additional consume attempt
        with pytest.raises(ModelCallBudgetExceededError):
            budget.consume()
        assert budget.max_calls == initial_max_calls
        assert budget.consumed_calls == initial_consumed_calls
        assert budget.remaining_calls == initial_remaining_calls
        assert budget.exhausted is True

        # Third additional consume attempt
        with pytest.raises(ModelCallBudgetExceededError):
            budget.consume()
        assert budget.max_calls == initial_max_calls
        assert budget.consumed_calls == initial_consumed_calls
        assert budget.remaining_calls == initial_remaining_calls
        assert budget.exhausted is True


class TestModelCallBudgetRemainingCallsNonNegative:
    """Test that remaining_calls is never negative."""

    def test_remaining_calls_never_negative(self) -> None:
        """remaining_calls should never be negative."""
        budget = ModelCallBudget(5)

        # Consume until exhausted
        for _ in range(5):
            budget.consume()

        assert budget.remaining_calls == 0

        # Try to consume after exhaustion
        with pytest.raises(ModelCallBudgetExceededError):
            budget.consume()

        # remaining_calls should still be 0
        assert budget.remaining_calls == 0


class TestModelCallBudgetBoundary:
    """Test max_calls=1 boundary."""

    def test_max_calls_one_boundary(self) -> None:
        """Test boundary behavior with max_calls=1."""
        budget = ModelCallBudget(1)

        assert budget.max_calls == 1
        assert budget.consumed_calls == 0
        assert budget.remaining_calls == 1
        assert budget.exhausted is False

        budget.consume()

        assert budget.max_calls == 1
        assert budget.consumed_calls == 1
        assert budget.remaining_calls == 0
        assert budget.exhausted is True

        with pytest.raises(ModelCallBudgetExceededError):
            budget.consume()


class TestModelCallBudgetPropertyDescriptors:
    """Test property descriptors."""

    def test_max_calls_is_property_descriptor(self) -> None:
        """max_calls is a property descriptor."""
        budget = ModelCallBudget(3)
        assert isinstance(type(budget).max_calls, property)

    def test_consumed_calls_is_property_descriptor(self) -> None:
        """consumed_calls is a property descriptor."""
        budget = ModelCallBudget(3)
        assert isinstance(type(budget).consumed_calls, property)

    def test_remaining_calls_is_property_descriptor(self) -> None:
        """remaining_calls is a property descriptor."""
        budget = ModelCallBudget(3)
        assert isinstance(type(budget).remaining_calls, property)

    def test_exhausted_is_property_descriptor(self) -> None:
        """exhausted is a property descriptor."""
        budget = ModelCallBudget(3)
        assert isinstance(type(budget).exhausted, property)

    def test_property_fset_is_none(self) -> None:
        """Property descriptors should have fset=None."""
        budget = ModelCallBudget(3)
        assert type(budget).max_calls.fset is None
        assert type(budget).consumed_calls.fset is None
        assert type(budget).remaining_calls.fset is None
        assert type(budget).exhausted.fset is None

    def test_assigning_max_calls_raises(self) -> None:
        """Assigning max_calls raises AttributeError."""
        budget = ModelCallBudget(3)
        with pytest.raises(AttributeError):
            budget.max_calls = 5

    def test_assigning_consumed_calls_raises(self) -> None:
        """Assigning consumed_calls raises AttributeError."""
        budget = ModelCallBudget(3)
        with pytest.raises(AttributeError):
            budget.consumed_calls = 5

    def test_assigning_remaining_calls_raises(self) -> None:
        """Assigning remaining_calls raises AttributeError."""
        budget = ModelCallBudget(3)
        with pytest.raises(AttributeError):
            budget.remaining_calls = 5

    def test_assigning_exhausted_raises(self) -> None:
        """Assigning exhausted raises AttributeError."""
        budget = ModelCallBudget(3)
        with pytest.raises(AttributeError):
            budget.exhausted = True


class TestModelCallBudgetConsumesSignature:
    """Test consume() signature."""

    def test_consume_signature(self) -> None:
        """inspect.signature(ModelCallBudget.consume) should contain exactly self."""
        sig = inspect.signature(ModelCallBudget.consume)
        params = list(sig.parameters.keys())
        assert params == ["self"]


class TestModelCallBudgetConsumeTypeError:
    """Test that budget.consume(2) raises TypeError."""

    def test_consume_with_argument_raises(self) -> None:
        """budget.consume(2) raises TypeError."""
        budget = ModelCallBudget(5)
        with pytest.raises(TypeError):
            budget.consume(2)


def test_phase_budget_reserves_calls_for_repair() -> None:
    from agent_platform.worker.execution_budget import (
        ModelCallPhaseBudgetExceededError,
        PhaseAwareModelCallBudget,
    )

    budget = PhaseAwareModelCallBudget(32)

    budget.begin_phase(24)

    for _ in range(24):
        budget.consume()

    with pytest.raises(ModelCallPhaseBudgetExceededError):
        budget.consume()

    assert budget.consumed_calls == 24
    assert budget.remaining_calls == 8

    budget.begin_phase(8)

    for _ in range(8):
        budget.consume()

    assert budget.consumed_calls == 32
    assert budget.remaining_calls == 0


def test_unused_initial_budget_is_available_to_repair() -> None:
    from agent_platform.worker.execution_budget import (
        PhaseAwareModelCallBudget,
    )

    budget = PhaseAwareModelCallBudget(32)

    budget.begin_phase(24)

    for _ in range(13):
        budget.consume()

    assert budget.remaining_calls == 19

    budget.begin_phase(budget.remaining_calls)

    assert budget.phase_max_calls == 19

    for _ in range(19):
        budget.consume()

    assert budget.consumed_calls == 32
    assert budget.remaining_calls == 0


def test_total_budget_remains_hard_limit_across_phases() -> None:
    from agent_platform.worker.execution_budget import (
        ModelCallBudgetExceededError,
        PhaseAwareModelCallBudget,
    )

    budget = PhaseAwareModelCallBudget(32)

    budget.begin_phase(24)

    for _ in range(24):
        budget.consume()

    budget.begin_phase(8)

    for _ in range(8):
        budget.consume()

    with pytest.raises(ModelCallBudgetExceededError):
        budget.consume()

    assert budget.consumed_calls == 32
    assert budget.remaining_calls == 0
