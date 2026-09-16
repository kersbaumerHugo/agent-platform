from collections.abc import Sequence

from agent_platform.contracts.evaluation import EvaluationContract
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
    EvaluationResult,
)


class EvalRunner:
    def __init__(self, evaluator: EvaluationContract) -> None:
        self.evaluator = evaluator

    async def run(
        self,
        cases: Sequence[EvaluationCase],
    ) -> list[EvaluationResult]:
        results: list[EvaluationResult] = []

        for case in cases:
            try:
                result = await self.evaluator.evaluate(case)
            except Exception as exc:
                result = EvaluationResult(
                    case_id=case.case_id,
                    evaluator=self.evaluator.name,
                    outcome=EvaluationOutcome.ERROR,
                    reason_code="evaluator_exception",
                    metadata={
                        "error_type": type(exc).__name__,
                    },
                )

            results.append(result)

        return results

    @staticmethod
    def summarize(
        results: Sequence[EvaluationResult],
    ) -> dict[str, int]:
        return {
            outcome.value: sum(result.outcome is outcome for result in results)
            for outcome in EvaluationOutcome
        }
