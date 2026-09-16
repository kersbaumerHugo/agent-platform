import pytest

from agent_platform.application.eval_runner import EvalRunner
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
    EvaluationResult,
)


class RecordingEvaluator:
    name = "recording"

    def __init__(self) -> None:
        self.seen_case_ids: list[str] = []

    async def evaluate(
        self,
        case: EvaluationCase,
    ) -> EvaluationResult:
        self.seen_case_ids.append(case.case_id)

        if case.case_id == "error":
            raise RuntimeError("boom")

        expected_outcome = case.expected.get("outcome", "pass")

        return EvaluationResult(
            case_id=case.case_id,
            evaluator=self.name,
            outcome=EvaluationOutcome(expected_outcome),
            reason_code="evaluated",
        )


@pytest.mark.asyncio
async def test_runner_executes_cases_in_input_order() -> None:
    evaluator = RecordingEvaluator()
    runner = EvalRunner(evaluator)

    cases = [
        EvaluationCase(
            case_id="first",
            expected={"outcome": "pass"},
        ),
        EvaluationCase(
            case_id="second",
            expected={"outcome": "fail"},
        ),
    ]

    results = await runner.run(cases)

    assert evaluator.seen_case_ids == ["first", "second"]
    assert [result.case_id for result in results] == [
        "first",
        "second",
    ]
    assert [result.outcome for result in results] == [
        EvaluationOutcome.PASS,
        EvaluationOutcome.FAIL,
    ]


@pytest.mark.asyncio
async def test_runner_converts_evaluator_exception_to_error_result() -> None:
    evaluator = RecordingEvaluator()
    runner = EvalRunner(evaluator)

    results = await runner.run(
        [
            EvaluationCase(case_id="error"),
            EvaluationCase(case_id="after-error"),
        ]
    )

    assert len(results) == 2

    error = results[0]
    assert error.case_id == "error"
    assert error.evaluator == "recording"
    assert error.outcome is EvaluationOutcome.ERROR
    assert error.reason_code == "evaluator_exception"
    assert error.metadata == {"error_type": "RuntimeError"}

    assert results[1].case_id == "after-error"
    assert results[1].outcome is EvaluationOutcome.PASS


@pytest.mark.asyncio
async def test_runner_accepts_empty_case_sequence() -> None:
    runner = EvalRunner(RecordingEvaluator())

    results = await runner.run([])

    assert results == []


def test_runner_summarizes_outcomes() -> None:
    results = [
        EvaluationResult(
            case_id="pass-1",
            evaluator="test",
            outcome=EvaluationOutcome.PASS,
            reason_code="ok",
        ),
        EvaluationResult(
            case_id="pass-2",
            evaluator="test",
            outcome=EvaluationOutcome.PASS,
            reason_code="ok",
        ),
        EvaluationResult(
            case_id="fail",
            evaluator="test",
            outcome=EvaluationOutcome.FAIL,
            reason_code="mismatch",
        ),
        EvaluationResult(
            case_id="error",
            evaluator="test",
            outcome=EvaluationOutcome.ERROR,
            reason_code="exception",
        ),
    ]

    summary = EvalRunner.summarize(results)

    assert summary == {
        "pass": 2,
        "fail": 1,
        "error": 1,
    }
