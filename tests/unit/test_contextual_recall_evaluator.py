from datetime import UTC, datetime
from uuid import UUID

import pytest

from agent_platform.adapters.evaluation.contextual_recall import (
    ContextualRecallEvaluator,
)
from agent_platform.application.retrieval_acceptance import (
    LexicalRetrievalAcceptanceGate,
)
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
)
from agent_platform.domain.memory import (
    MemoryRecord,
    MemoryScope,
    RetrievalHit,
    RetrievalQuery,
)


def make_hit(
    *,
    memory_id: str,
    namespace: str,
    content: str,
) -> RetrievalHit:
    return RetrievalHit(
        memory=MemoryRecord(
            id=UUID(memory_id),
            scope=MemoryScope(namespace=namespace),
            content=content,
            created_at=datetime(
                2026,
                9,
                16,
                12,
                0,
                tzinfo=UTC,
            ),
        ),
        score=1.0,
        rank=1,
    )


class StaticRetrieval:
    def __init__(
        self,
        hits_by_namespace: dict[str, list[RetrievalHit]],
    ) -> None:
        self._hits_by_namespace = hits_by_namespace

    async def retrieve(
        self,
        query: RetrievalQuery,
    ) -> list[RetrievalHit]:
        return list(
            self._hits_by_namespace.get(
                query.scope.namespace,
                [],
            )
        )


def make_evaluator() -> ContextualRecallEvaluator:
    return ContextualRecallEvaluator(
        retrieval=StaticRetrieval(
            {
                "global": [
                    make_hit(
                        memory_id=("11111111-1111-1111-1111-111111111111"),
                        namespace="global",
                        content="context signal global",
                    )
                ],
                "app:linkedin": [
                    make_hit(
                        memory_id=("22222222-2222-2222-2222-222222222222"),
                        namespace="app:linkedin",
                        content="context signal linkedin",
                    )
                ],
                "project:homelab": [
                    make_hit(
                        memory_id=("33333333-3333-3333-3333-333333333333"),
                        namespace="project:homelab",
                        content="context signal homelab",
                    )
                ],
                "project:agent-platform": [
                    make_hit(
                        memory_id=("44444444-4444-4444-4444-444444444444"),
                        namespace="project:agent-platform",
                        content="context signal agent platform",
                    )
                ],
            }
        ),
        acceptance=LexicalRetrievalAcceptanceGate(),
    )


@pytest.mark.asyncio
async def test_evaluator_passes_for_explicit_context_allow_list() -> None:
    evaluator = make_evaluator()

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="linkedin-homelab",
            input={
                "contexts": [
                    {
                        "role": "shared",
                        "namespace": "global",
                    },
                    {
                        "role": "delivery",
                        "namespace": "app:linkedin",
                    },
                    {
                        "role": "subject",
                        "namespace": "project:homelab",
                    },
                ],
                "query": "context signal",
            },
            expected={
                "queried_namespaces": [
                    "global",
                    "app:linkedin",
                    "project:homelab",
                ],
                "contexts": [
                    {
                        "context": {
                            "role": "shared",
                            "namespace": "global",
                        },
                        "decision": "accept",
                        "memory_ids": [("11111111-1111-1111-1111-111111111111")],
                    },
                    {
                        "context": {
                            "role": "delivery",
                            "namespace": "app:linkedin",
                        },
                        "decision": "accept",
                        "memory_ids": [("22222222-2222-2222-2222-222222222222")],
                    },
                    {
                        "context": {
                            "role": "subject",
                            "namespace": "project:homelab",
                        },
                        "decision": "accept",
                        "memory_ids": [("33333333-3333-3333-3333-333333333333")],
                    },
                ],
            },
        )
    )

    assert result.outcome is EvaluationOutcome.PASS
    assert result.metrics["query_sequence_match"] == 1.0
    assert result.metrics["unexpected_query_count"] == 0.0
    assert result.metadata["actual_queried_namespaces"] == [
        "global",
        "app:linkedin",
        "project:homelab",
    ]
    assert "project:agent-platform" not in result.metadata["actual_queried_namespaces"]


@pytest.mark.asyncio
async def test_evaluator_preserves_abstention_as_empty_memory() -> None:
    evaluator = ContextualRecallEvaluator(
        retrieval=StaticRetrieval(
            {
                "app:linkedin": [
                    make_hit(
                        memory_id=("22222222-2222-2222-2222-222222222222"),
                        namespace="app:linkedin",
                        content="unrelated writing preference",
                    )
                ]
            }
        ),
        acceptance=LexicalRetrievalAcceptanceGate(),
    )

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="abstained-context",
            input={
                "contexts": [
                    {
                        "role": "delivery",
                        "namespace": "app:linkedin",
                    }
                ],
                "query": "context signal",
            },
            expected={
                "queried_namespaces": [
                    "app:linkedin",
                ],
                "contexts": [
                    {
                        "context": {
                            "role": "delivery",
                            "namespace": "app:linkedin",
                        },
                        "decision": "abstain",
                        "memory_ids": [],
                    }
                ],
            },
        )
    )

    assert result.outcome is EvaluationOutcome.PASS
    assert result.metrics["decision_match"] == 1.0
    assert result.metrics["memory_ids_match"] == 1.0


@pytest.mark.asyncio
async def test_evaluator_fails_when_expected_query_allow_list_is_wrong() -> None:
    evaluator = make_evaluator()

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="unexpected-query-detection",
            input={
                "contexts": [
                    {
                        "role": "delivery",
                        "namespace": "app:linkedin",
                    },
                    {
                        "role": "subject",
                        "namespace": "project:homelab",
                    },
                ],
                "query": "context signal",
            },
            expected={
                "queried_namespaces": [
                    "app:linkedin",
                ],
                "contexts": [
                    {
                        "context": {
                            "role": "delivery",
                            "namespace": "app:linkedin",
                        },
                        "decision": "accept",
                        "memory_ids": [("22222222-2222-2222-2222-222222222222")],
                    },
                    {
                        "context": {
                            "role": "subject",
                            "namespace": "project:homelab",
                        },
                        "decision": "accept",
                        "memory_ids": [("33333333-3333-3333-3333-333333333333")],
                    },
                ],
            },
        )
    )

    assert result.outcome is EvaluationOutcome.FAIL
    assert result.metrics["query_sequence_match"] == 0.0
    assert result.metrics["unexpected_query_count"] == 1.0
