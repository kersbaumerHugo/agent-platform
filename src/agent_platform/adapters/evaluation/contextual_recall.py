from collections import Counter
from uuid import UUID

from pydantic import BaseModel, Field

from agent_platform.application.contextual_recall import ContextualRecall
from agent_platform.contracts.memory import (
    RetrievalAcceptanceContract,
    RetrievalContract,
)
from agent_platform.domain.context import ContextRef
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
    EvaluationResult,
)
from agent_platform.domain.memory import (
    RetrievalDecision,
    RetrievalHit,
    RetrievalQuery,
)


class ContextualRecallEvaluationInput(BaseModel):
    contexts: list[ContextRef] = Field(default_factory=list)
    query: str = Field(min_length=1)
    limit_per_context: int = Field(default=5, gt=0)


class ContextualRecallExpectedContext(BaseModel):
    context: ContextRef
    decision: RetrievalDecision
    memory_ids: list[UUID] = Field(default_factory=list)


class ContextualRecallEvaluationExpected(BaseModel):
    queried_namespaces: list[str] = Field(default_factory=list)
    contexts: list[ContextualRecallExpectedContext] = Field(default_factory=list)


class _RecordingRetrieval:
    def __init__(self, delegate: RetrievalContract) -> None:
        self._delegate = delegate
        self.queries: list[RetrievalQuery] = []

    async def retrieve(
        self,
        query: RetrievalQuery,
    ) -> list[RetrievalHit]:
        self.queries.append(query)
        return await self._delegate.retrieve(query)


class ContextualRecallEvaluator:
    name = "contextual_recall"

    def __init__(
        self,
        *,
        retrieval: RetrievalContract,
        acceptance: RetrievalAcceptanceContract,
    ) -> None:
        self._retrieval = retrieval
        self._acceptance = acceptance

    async def evaluate(
        self,
        case: EvaluationCase,
    ) -> EvaluationResult:
        evaluation_input = ContextualRecallEvaluationInput.model_validate(
            case.input,
        )
        expected = ContextualRecallEvaluationExpected.model_validate(
            case.expected,
        )

        recording_retrieval = _RecordingRetrieval(
            self._retrieval,
        )
        recall = ContextualRecall(
            retrieval=recording_retrieval,
            acceptance=self._acceptance,
        )

        results = await recall.recall(
            contexts=evaluation_input.contexts,
            text=evaluation_input.query,
            limit_per_context=(evaluation_input.limit_per_context),
        )

        actual_queried_namespaces = [query.scope.namespace for query in recording_retrieval.queries]
        query_sequence_match = actual_queried_namespaces == expected.queried_namespaces

        expected_query_counts = Counter(expected.queried_namespaces)
        actual_query_counts = Counter(actual_queried_namespaces)
        unexpected_query_count = sum(
            max(
                0,
                actual_count - expected_query_counts[namespace],
            )
            for namespace, actual_count in actual_query_counts.items()
        )

        result_count_match = len(results) == len(expected.contexts)

        context_order_match = result_count_match and all(
            actual.context == expected_context.context
            for actual, expected_context in zip(
                results,
                expected.contexts,
                strict=True,
            )
        )

        decision_match = result_count_match and all(
            actual.decision.decision is expected_context.decision
            for actual, expected_context in zip(
                results,
                expected.contexts,
                strict=True,
            )
        )

        memory_ids_match = result_count_match and all(
            [hit.memory.id for hit in actual.hits] == expected_context.memory_ids
            for actual, expected_context in zip(
                results,
                expected.contexts,
                strict=True,
            )
        )

        expectations_met = all(
            (
                query_sequence_match,
                result_count_match,
                context_order_match,
                decision_match,
                memory_ids_match,
                unexpected_query_count == 0,
            )
        )

        return EvaluationResult(
            case_id=case.case_id,
            evaluator=self.name,
            outcome=(EvaluationOutcome.PASS if expectations_met else EvaluationOutcome.FAIL),
            reason_code=("expectations_met" if expectations_met else "expectation_mismatch"),
            metrics={
                "query_sequence_match": float(query_sequence_match),
                "result_count_match": float(result_count_match),
                "context_order_match": float(context_order_match),
                "decision_match": float(decision_match),
                "memory_ids_match": float(memory_ids_match),
                "unexpected_query_count": float(unexpected_query_count),
            },
            metadata={
                "actual_queried_namespaces": (actual_queried_namespaces),
                "actual_contexts": [
                    {
                        "context": result.context.model_dump(mode="json"),
                        "decision": (result.decision.decision.value),
                        "reason_code": (result.decision.reason_code),
                        "memory_ids": [str(hit.memory.id) for hit in result.hits],
                    }
                    for result in results
                ],
            },
        )
