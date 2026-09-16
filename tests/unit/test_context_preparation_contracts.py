import pytest
from pydantic import ValidationError

from agent_platform.domain.context import ContextRef, ContextRole
from agent_platform.domain.context_preparation import (
    RecallIntent,
    RecallPlan,
    RecallRequest,
)


def make_context(
    *,
    role: ContextRole = ContextRole.SUBJECT,
    namespace: str = "project:homelab",
) -> ContextRef:
    return ContextRef(
        role=role,
        namespace=namespace,
    )


def test_recall_intent_preserves_objective_step_and_context_order() -> None:
    contexts = (
        make_context(
            role=ContextRole.SHARED,
            namespace="global",
        ),
        make_context(
            role=ContextRole.DELIVERY,
            namespace="app:linkedin",
        ),
        make_context(
            role=ContextRole.SUBJECT,
            namespace="project:homelab",
        ),
    )

    intent = RecallIntent(
        objective="Write a LinkedIn post about the homelab.",
        step_input="Draft the post.",
        contexts=contexts,
    )

    assert intent.objective == "Write a LinkedIn post about the homelab."
    assert intent.step_input == "Draft the post."
    assert intent.contexts == contexts


def test_recall_intent_rejects_duplicate_contexts() -> None:
    context = make_context()

    with pytest.raises(
        ValidationError,
        match="contexts must be unique by role and namespace",
    ):
        RecallIntent(
            objective="Do work.",
            step_input="Execute.",
            contexts=(
                context,
                context,
            ),
        )


def test_recall_intent_can_have_no_contexts() -> None:
    intent = RecallIntent(
        objective="Do work.",
        step_input="Execute.",
    )

    assert intent.contexts == ()


def test_recall_request_is_provider_neutral() -> None:
    context = make_context()

    request = RecallRequest(
        request_id="subject-task-relevant",
        context=context,
        query="homelab observability",
        limit=3,
    )

    assert request.context == context
    assert request.query == "homelab observability"
    assert request.limit == 3


def test_recall_request_requires_positive_limit() -> None:
    with pytest.raises(ValidationError):
        RecallRequest(
            request_id="invalid",
            context=make_context(),
            query="context",
            limit=0,
        )


def test_recall_plan_preserves_request_order() -> None:
    global_context = make_context(
        role=ContextRole.SHARED,
        namespace="global",
    )
    subject_context = make_context()

    requests = (
        RecallRequest(
            request_id="shared",
            context=global_context,
            query="writing preferences",
        ),
        RecallRequest(
            request_id="subject",
            context=subject_context,
            query="homelab observability",
        ),
    )

    plan = RecallPlan(
        planner="deterministic",
        version="v0",
        requests=requests,
    )

    assert plan.planner == "deterministic"
    assert plan.version == "v0"
    assert plan.requests == requests


def test_recall_plan_allows_multiple_requests_for_same_context() -> None:
    context = make_context()

    plan = RecallPlan(
        planner="deterministic",
        version="v0",
        requests=(
            RecallRequest(
                request_id="subject-standing",
                context=context,
                query="architecture decisions",
            ),
            RecallRequest(
                request_id="subject-task-relevant",
                context=context,
                query="observability",
            ),
        ),
    )

    assert len(plan.requests) == 2
    assert all(request.context == context for request in plan.requests)


def test_recall_plan_rejects_duplicate_request_ids() -> None:
    context = make_context()

    with pytest.raises(
        ValidationError,
        match="request_id values must be unique",
    ):
        RecallPlan(
            planner="deterministic",
            version="v0",
            requests=(
                RecallRequest(
                    request_id="duplicate",
                    context=context,
                    query="first",
                ),
                RecallRequest(
                    request_id="duplicate",
                    context=context,
                    query="second",
                ),
            ),
        )


def test_recall_plan_can_be_empty() -> None:
    plan = RecallPlan(
        planner="deterministic",
        version="v0",
    )

    assert plan.requests == ()


def test_fixed_recall_plan_serialization_is_stable() -> None:
    plan = RecallPlan(
        planner="deterministic",
        version="v0",
        requests=(
            RecallRequest(
                request_id="subject",
                context=make_context(),
                query="homelab observability",
            ),
        ),
    )

    assert plan.model_dump_json() == plan.model_dump_json()
