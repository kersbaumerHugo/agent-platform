from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from agent_platform.adapters.evaluation.retrieval import (
    RetrievalEvaluator,
)
from agent_platform.application.eval_runner import EvalRunner
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
)
from agent_platform.domain.memory import (
    MemoryRecord,
    MemoryScope,
    RetrievalAcceptanceDecision,
    RetrievalDecision,
    RetrievalHit,
    RetrievalQuery,
)


class FakeRetrieval:
    def __init__(
        self,
        hits: list[RetrievalHit],
    ) -> None:
        self.hits = hits
        self.queries: list[RetrievalQuery] = []

    async def retrieve(
        self,
        query: RetrievalQuery,
    ) -> list[RetrievalHit]:
        self.queries.append(query)
        return self.hits


class FakeAcceptance:
    def __init__(
        self,
        decision: RetrievalDecision,
        reason_code: str,
    ) -> None:
        self.decision = decision
        self.reason_code = reason_code

    async def evaluate(
        self,
        query: RetrievalQuery,
        hits: Sequence[RetrievalHit],
    ) -> RetrievalAcceptanceDecision:
        return RetrievalAcceptanceDecision(
            decision=self.decision,
            reason_code=self.reason_code,
            metadata={
                "hit_count": len(hits),
            },
        )


def make_hit(
    *,
    memory_id: UUID,
    rank: int,
    score: float,
) -> RetrievalHit:
    return RetrievalHit(
        memory=MemoryRecord(
            id=memory_id,
            scope=MemoryScope(namespace="test"),
            content=f"memory-{rank}",
            created_at=datetime.now(UTC),
        ),
        score=score,
        rank=rank,
    )


@pytest.mark.asyncio
async def test_relevant_query_passes_expected_recall_and_top_1() -> None:
    expected_id = uuid4()

    evaluator = RetrievalEvaluator(
        retrieval=FakeRetrieval(
            [
                make_hit(
                    memory_id=expected_id,
                    rank=1,
                    score=1.0,
                ),
            ]
        ),
        acceptance=FakeAcceptance(
            RetrievalDecision.ACCEPT,
            "lexical_evidence",
        ),
    )

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="relevant-query",
            input={
                "namespace": "test",
                "query": "local inference",
                "limit": 5,
            },
            expected={
                "decision": "accept",
                "memory_ids": [str(expected_id)],
                "top_memory_id": str(expected_id),
            },
        )
    )

    assert result.outcome is EvaluationOutcome.PASS
    assert result.reason_code == "expectations_met"
    assert result.metrics["decision_match"] == 1.0
    assert result.metrics["expected_memory_recall_at_k"] == 1.0
    assert result.metrics["top_1_correct"] == 1.0
    assert result.metrics["hit_count"] == 1.0
    assert result.metadata["actual_decision"] == "accept"
    assert result.metadata["acceptance_reason_code"] == "lexical_evidence"


@pytest.mark.asyncio
async def test_unrelated_query_passes_expected_abstention() -> None:
    evaluator = RetrievalEvaluator(
        retrieval=FakeRetrieval([]),
        acceptance=FakeAcceptance(
            RetrievalDecision.ABSTAIN,
            "no_hits",
        ),
    )

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="unrelated-query",
            input={
                "namespace": "test",
                "query": "kubernetes autoscaling",
            },
            expected={
                "decision": "abstain",
            },
        )
    )

    assert result.outcome is EvaluationOutcome.PASS
    assert result.metrics == {
        "decision_match": 1.0,
        "hit_count": 0.0,
    }


@pytest.mark.asyncio
async def test_missing_expected_memory_fails_recall_expectation() -> None:
    expected_id = uuid4()
    other_id = uuid4()

    evaluator = RetrievalEvaluator(
        retrieval=FakeRetrieval(
            [
                make_hit(
                    memory_id=other_id,
                    rank=1,
                    score=1.0,
                )
            ]
        ),
        acceptance=FakeAcceptance(
            RetrievalDecision.ACCEPT,
            "lexical_evidence",
        ),
    )

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="missing-memory",
            input={
                "namespace": "test",
                "query": "local inference",
            },
            expected={
                "decision": "accept",
                "memory_ids": [str(expected_id)],
            },
        )
    )

    assert result.outcome is EvaluationOutcome.FAIL
    assert result.reason_code == "expectation_mismatch"
    assert result.metrics["decision_match"] == 1.0
    assert result.metrics["expected_memory_recall_at_k"] == 0.0


@pytest.mark.asyncio
async def test_wrong_top_1_fails_even_when_expected_memory_is_recalled() -> None:
    expected_id = uuid4()
    other_id = uuid4()

    evaluator = RetrievalEvaluator(
        retrieval=FakeRetrieval(
            [
                make_hit(
                    memory_id=other_id,
                    rank=1,
                    score=2.0,
                ),
                make_hit(
                    memory_id=expected_id,
                    rank=2,
                    score=1.0,
                ),
            ]
        ),
        acceptance=FakeAcceptance(
            RetrievalDecision.ACCEPT,
            "lexical_evidence",
        ),
    )

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="wrong-top-1",
            input={
                "namespace": "test",
                "query": "local inference",
            },
            expected={
                "decision": "accept",
                "memory_ids": [str(expected_id)],
                "top_memory_id": str(expected_id),
            },
        )
    )

    assert result.outcome is EvaluationOutcome.FAIL
    assert result.metrics["expected_memory_recall_at_k"] == 1.0
    assert result.metrics["top_1_correct"] == 0.0


@pytest.mark.asyncio
async def test_eval_runner_can_execute_retrieval_evaluator() -> None:
    evaluator = RetrievalEvaluator(
        retrieval=FakeRetrieval([]),
        acceptance=FakeAcceptance(
            RetrievalDecision.ABSTAIN,
            "no_hits",
        ),
    )
    runner = EvalRunner(evaluator)

    results = await runner.run(
        [
            EvaluationCase(
                case_id="runner-composition",
                input={
                    "namespace": "test",
                    "query": "unrelated",
                },
                expected={
                    "decision": "abstain",
                },
            )
        ]
    )

    assert len(results) == 1
    assert results[0].outcome is EvaluationOutcome.PASS


@pytest.mark.asyncio
async def test_invalid_retrieval_case_is_reported_as_runner_error() -> None:
    evaluator = RetrievalEvaluator(
        retrieval=FakeRetrieval([]),
        acceptance=FakeAcceptance(
            RetrievalDecision.ABSTAIN,
            "no_hits",
        ),
    )
    runner = EvalRunner(evaluator)

    results = await runner.run(
        [
            EvaluationCase(
                case_id="invalid",
                input={
                    "namespace": "",
                    "query": "query",
                },
                expected={
                    "decision": "abstain",
                },
            )
        ]
    )

    assert len(results) == 1
    assert results[0].outcome is EvaluationOutcome.ERROR
    assert results[0].reason_code == "evaluator_exception"
    assert results[0].metadata == {
        "error_type": ValidationError.__name__,
    }
