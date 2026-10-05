import pytest

from agent_platform.trust.goal_acceptance import (
    GoalAcceptanceEvaluator,
    GoalAcceptanceOutcome,
    GoalAcceptanceResult,
)


def test_no_change_is_rejected() -> None:
    result = GoalAcceptanceEvaluator().evaluate(
        changed_paths=(),
    )

    assert not result.accepted
    assert result.outcome is GoalAcceptanceOutcome.REJECT
    assert result.reason_code == "required_change_missing"


def test_blank_paths_do_not_count_as_changes() -> None:
    result = GoalAcceptanceEvaluator().evaluate(
        changed_paths=("", "   "),
    )

    assert not result.accepted
    assert result.reason_code == "required_change_missing"


def test_real_change_is_accepted_for_h0e1() -> None:
    result = GoalAcceptanceEvaluator().evaluate(
        changed_paths=("tests/unit/test_example.py",),
    )

    assert result.accepted
    assert result.outcome is GoalAcceptanceOutcome.ACCEPT
    assert result.reason_code == "change_present"


def test_result_requires_reason_code() -> None:
    with pytest.raises(
        ValueError,
        match="reason_code",
    ):
        GoalAcceptanceResult(
            outcome=GoalAcceptanceOutcome.REJECT,
            reason_code="",
        )
