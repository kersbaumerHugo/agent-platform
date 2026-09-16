from math import nan

import pytest
from pydantic import ValidationError

from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
    EvaluationResult,
)


def test_evaluation_case_accepts_reusable_structured_data() -> None:
    case = EvaluationCase(
        case_id="retrieval-relevant-query",
        input={
            "namespace": "test",
            "query": "local inference",
        },
        expected={
            "decision": "accept",
            "memory_ids": ["memory-123"],
        },
        metadata={"suite": "retrieval-v0"},
    )

    assert case.case_id == "retrieval-relevant-query"
    assert case.input["namespace"] == "test"
    assert case.expected["decision"] == "accept"
    assert case.metadata["suite"] == "retrieval-v0"


def test_evaluation_case_rejects_empty_case_id() -> None:
    with pytest.raises(ValidationError):
        EvaluationCase(case_id="")


def test_evaluation_case_uses_independent_default_mappings() -> None:
    first = EvaluationCase(case_id="first")
    second = EvaluationCase(case_id="second")

    first.metadata["source"] = "first"

    assert second.metadata == {}


def test_evaluation_result_supports_pass_fail_and_error() -> None:
    for outcome in EvaluationOutcome:
        result = EvaluationResult(
            case_id="case-1",
            evaluator="deterministic",
            outcome=outcome,
            reason_code="evaluated",
        )

        assert result.outcome is outcome


def test_evaluation_result_accepts_finite_metrics() -> None:
    result = EvaluationResult(
        case_id="case-1",
        evaluator="retrieval",
        outcome=EvaluationOutcome.PASS,
        reason_code="expected_result",
        metrics={
            "recall_at_5": 1.0,
            "latency_ms": 12.5,
        },
    )

    assert result.metrics["recall_at_5"] == 1.0
    assert result.metrics["latency_ms"] == 12.5


def test_evaluation_result_rejects_non_finite_metrics() -> None:
    with pytest.raises(ValidationError):
        EvaluationResult(
            case_id="case-1",
            evaluator="retrieval",
            outcome=EvaluationOutcome.FAIL,
            reason_code="invalid_metric",
            metrics={"score": nan},
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("case_id", ""),
        ("evaluator", ""),
        ("reason_code", ""),
    ],
)
def test_evaluation_result_rejects_empty_required_strings(
    field: str,
    value: str,
) -> None:
    data = {
        "case_id": "case-1",
        "evaluator": "deterministic",
        "outcome": EvaluationOutcome.PASS,
        "reason_code": "evaluated",
    }
    data[field] = value

    with pytest.raises(ValidationError):
        EvaluationResult(**data)
