from uuid import UUID

from pydantic import BaseModel, Field

from agent_platform.contracts.memory import (
    RetrievalAcceptanceContract,
    RetrievalContract,
)
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
    EvaluationResult,
)
from agent_platform.domain.memory import (
    MemoryScope,
    RetrievalDecision,
    RetrievalQuery,
)


class RetrievalEvaluationInput(BaseModel):
    namespace: str = Field(min_length=1)
    query: str = Field(min_length=1)
    limit: int = Field(default=5, gt=0)


class RetrievalEvaluationExpected(BaseModel):
    decision: RetrievalDecision
    memory_ids: list[UUID] = Field(default_factory=list)
    top_memory_id: UUID | None = None


class RetrievalEvaluator:
    name = "retrieval"

    def __init__(
        self,
        retrieval: RetrievalContract,
        acceptance: RetrievalAcceptanceContract,
    ) -> None:
        self.retrieval = retrieval
        self.acceptance = acceptance

    async def evaluate(
        self,
        case: EvaluationCase,
    ) -> EvaluationResult:
        evaluation_input = RetrievalEvaluationInput.model_validate(
            case.input,
        )
        expected = RetrievalEvaluationExpected.model_validate(
            case.expected,
        )

        query = RetrievalQuery(
            scope=MemoryScope(
                namespace=evaluation_input.namespace,
            ),
            text=evaluation_input.query,
            limit=evaluation_input.limit,
        )

        hits = await self.retrieval.retrieve(query)
        acceptance = await self.acceptance.evaluate(
            query,
            hits,
        )

        actual_memory_ids = [hit.memory.id for hit in hits]

        decision_match = acceptance.decision is expected.decision
        expectations_met = decision_match

        metrics: dict[str, float] = {
            "decision_match": float(decision_match),
            "hit_count": float(len(hits)),
        }

        if expected.memory_ids:
            expected_memory_ids = set(expected.memory_ids)
            actual_memory_id_set = set(actual_memory_ids)
            matched_memory_ids = expected_memory_ids & actual_memory_id_set
            recall_at_k = len(matched_memory_ids) / len(expected_memory_ids)

            metrics["expected_memory_recall_at_k"] = recall_at_k
            expectations_met = expectations_met and recall_at_k == 1.0

        if expected.top_memory_id is not None:
            top_1_correct = (
                bool(actual_memory_ids) and actual_memory_ids[0] == expected.top_memory_id
            )

            metrics["top_1_correct"] = float(top_1_correct)
            expectations_met = expectations_met and top_1_correct

        return EvaluationResult(
            case_id=case.case_id,
            evaluator=self.name,
            outcome=(EvaluationOutcome.PASS if expectations_met else EvaluationOutcome.FAIL),
            reason_code=("expectations_met" if expectations_met else "expectation_mismatch"),
            metrics=metrics,
            metadata={
                "actual_decision": acceptance.decision.value,
                "expected_decision": expected.decision.value,
                "acceptance_reason_code": (acceptance.reason_code),
            },
        )
