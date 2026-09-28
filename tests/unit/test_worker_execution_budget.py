"""Tests for ModelRequestBudget and ModelRequestBudgetExceededError."""

import pytest

from agent_platform.worker.execution_budget import (
    ModelRequestBudget,
    ModelRequestBudgetExceededError,
)


class TestModelRequestBudget:
    """Tests for ModelRequestBudget."""

    def test_create_default_budget(self) -> None:
        """Test creating a budget with defaults."""
        budget = ModelRequestBudget(max_total_tokens=1000)
        assert budget.max_total_tokens == 1000
        assert budget.base_input_tokens == 0
        assert budget.reserved_output_tokens == 0
        assert budget.available_model_tokens == 1000
        assert budget.remaining_tokens == 1000

    def test_create_with_custom_values(self) -> None:
        """Test creating a budget with custom input and reserved tokens."""
        budget = ModelRequestBudget(
            max_total_tokens=1000,
            base_input_tokens=100,
            reserved_output_tokens=200,
        )
        assert budget.max_total_tokens == 1000
        assert budget.base_input_tokens == 100
        assert budget.reserved_output_tokens == 200
        assert budget.available_model_tokens == 700
        assert budget.remaining_tokens == 700

    def test_available_model_tokens_property(self) -> None:
        """Test available_model_tokens property."""
        budget = ModelRequestBudget(max_total_tokens=1000, base_input_tokens=100)
        assert budget.available_model_tokens == 900

    def test_remaining_tokens_property(self) -> None:
        """Test remaining_tokens property returns available tokens."""
        budget = ModelRequestBudget(
            max_total_tokens=1000,
            base_input_tokens=100,
            reserved_output_tokens=200,
        )
        # remaining_tokens equals available_model_tokens for frozen budget
        assert budget.remaining_tokens == 700

    def test_validate_reserved_capacity(self) -> None:
        """Test that reserved capacity cannot exceed max_total_tokens."""
        with pytest.raises(ValueError, match="must not exceed max_total_tokens"):
            ModelRequestBudget(
                max_total_tokens=1000,
                base_input_tokens=800,
                reserved_output_tokens=500,
            )

    def test_validate_reserved_capacity_exact(self) -> None:
        """Test that reserved capacity can equal max_total_tokens."""
        budget = ModelRequestBudget(
            max_total_tokens=1000,
            base_input_tokens=500,
            reserved_output_tokens=500,
        )
        assert budget.available_model_tokens == 0

    def test_frozen_model(self) -> None:
        """Test that ModelRequestBudget is frozen."""
        budget = ModelRequestBudget(max_total_tokens=1000)
        with pytest.raises(ValueError):
            budget.max_total_tokens = 2000

    def test_max_total_tokens_must_be_positive(self) -> None:
        """Test that max_total_tokens must be positive."""
        with pytest.raises(ValueError, match="greater than 0"):
            ModelRequestBudget(max_total_tokens=0)

    def test_base_input_tokens_can_be_zero(self) -> None:
        """Test that base_input_tokens can be zero."""
        budget = ModelRequestBudget(max_total_tokens=1000, base_input_tokens=0)
        assert budget.available_model_tokens == 1000


class TestModelRequestBudgetExceededError:
    """Tests for ModelRequestBudgetExceededError."""

    def test_error_with_default_message(self) -> None:
        """Test error creation with default message."""
        error = ModelRequestBudgetExceededError(
            budget=1000,
            used=1100,
        )
        assert error.budget == 1000
        assert error.used == 1100
        assert "Model request budget exceeded" in str(error)
        assert "1100 tokens used" in str(error)
        assert "1000 tokens budget" in str(error)

    def test_error_with_custom_message(self) -> None:
        """Test error creation with custom message."""
        error = ModelRequestBudgetExceededError(
            budget=1000,
            used=1100,
            message="Custom budget exceeded message",
        )
        assert error.budget == 1000
        assert error.used == 1100
        assert "Custom budget exceeded message" in str(error)

    def test_error_with_request_id(self) -> None:
        """Test error creation with request ID."""
        error = ModelRequestBudgetExceededError(
            budget=1000,
            used=1100,
            request_id="request-123",
        )
        assert error.request_id == "request-123"

    def test_error_inheritance(self) -> None:
        """Test that ModelRequestBudgetExceededError is a ValueError."""
        assert issubclass(ModelRequestBudgetExceededError, ValueError)

    def test_error_values_accessible(self) -> None:
        """Test that error values are accessible."""
        error = ModelRequestBudgetExceededError(
            budget=500,
            used=450,
            request_id="test-req-1",
        )
        assert error.budget == 500
        assert error.used == 450
        assert error.request_id == "test-req-1"


class TestModelRequestBudgetIntegration:
    """Integration tests for ModelRequestBudget."""

    def test_zero_available_budget(self) -> None:
        """Test budget with zero available tokens."""
        budget = ModelRequestBudget(
            max_total_tokens=1000,
            base_input_tokens=500,
            reserved_output_tokens=500,
        )
        assert budget.available_model_tokens == 0

    def test_large_budget(self) -> None:
        """Test budget with large values."""
        budget = ModelRequestBudget(max_total_tokens=10_000_000)
        assert budget.available_model_tokens == 10_000_000

    def test_budget_with_all_tokens_reserved(self) -> None:
        """Test budget when all tokens are reserved."""
        budget = ModelRequestBudget(
            max_total_tokens=100,
            base_input_tokens=50,
            reserved_output_tokens=50,
        )
        assert budget.available_model_tokens == 0
        assert budget.remaining_tokens == 0

    def test_budget_validation_on_creation(self) -> None:
        """Test that budget validates reserved capacity on creation."""
        # This should pass - reserved capacity equals max_total_tokens
        budget = ModelRequestBudget(
            max_total_tokens=100,
            base_input_tokens=50,
            reserved_output_tokens=50,
        )
        assert budget.available_model_tokens == 0
