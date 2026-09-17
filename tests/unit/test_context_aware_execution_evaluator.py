import pytest

from agent_platform.adapters.evaluation.context_aware_execution import (
    ContextAwareExecutionEvaluator,
)
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
)


@pytest.mark.asyncio
async def test_context_aware_work_case_passes() -> None:
    evaluator = ContextAwareExecutionEvaluator()

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="context-aware-work",
            input={
                "scenario": "work",
                "work": {
                    "objective": "Write about the homelab.",
                    "contexts": [
                        {
                            "role": "subject",
                            "namespace": "project:homelab",
                        }
                    ],
                    "steps": [
                        {
                            "step_id": "draft",
                            "agent_id": "writer",
                            "input": "Draft the post.",
                        }
                    ],
                },
            },
            expected={
                "work_status": "succeeded",
                "executed_step_ids": ["draft"],
                "run_statuses": ["succeeded"],
                "trace_present": [True],
                "traced_contexts": [
                    [
                        {
                            "role": "subject",
                            "namespace": "project:homelab",
                        }
                    ]
                ],
                "bindings_cleared": True,
                "runtime_context_present": [True],
                "runtime_required": [True],
                "distinct_run_ids": True,
            },
        )
    )

    assert result.outcome is EvaluationOutcome.PASS
    assert result.reason_code == "expectations_met"
    assert result.metrics["bindings_cleared_match"] == 1.0
    assert result.metrics["traced_contexts_match"] == 1.0


@pytest.mark.asyncio
async def test_missing_required_binding_case_passes() -> None:
    evaluator = ContextAwareExecutionEvaluator()

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="missing-required-binding",
            input={
                "scenario": "missing_binding",
            },
            expected={
                "gateway_status_code": 503,
                "gateway_error_type": ("required_context_binding_missing"),
                "bindings_cleared": True,
            },
        )
    )

    assert result.outcome is EvaluationOutcome.PASS
    assert result.metadata["facts"]["gateway_status_code"] == 503
    assert result.metadata["facts"]["gateway_error_type"] == "required_context_binding_missing"


@pytest.mark.asyncio
async def test_concurrent_isolation_case_passes() -> None:
    evaluator = ContextAwareExecutionEvaluator()

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="concurrent-isolation",
            input={
                "scenario": "concurrent_isolation",
            },
            expected={
                "isolated": True,
                "context_message_counts": [1, 1],
                "bindings_cleared": True,
            },
        )
    )

    assert result.outcome is EvaluationOutcome.PASS
    assert result.metrics["isolated_match"] == 1.0
    assert result.metrics["context_message_counts_match"] == 1.0


@pytest.mark.asyncio
async def test_expectation_mismatch_returns_fail() -> None:
    evaluator = ContextAwareExecutionEvaluator()

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="intentional-mismatch",
            input={
                "scenario": "missing_binding",
            },
            expected={
                "gateway_status_code": 503,
                "gateway_error_type": ("required_context_binding_missing"),
                "bindings_cleared": False,
            },
        )
    )

    assert result.outcome is EvaluationOutcome.FAIL
    assert result.reason_code == "expectation_mismatch"
    assert result.metrics["bindings_cleared_match"] == 0.0
