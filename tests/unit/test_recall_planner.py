import pytest

from agent_platform.application.recall_planner import (
    DeterministicRecallPlanner,
)
from agent_platform.contracts.context import RecallPlannerContract
from agent_platform.domain.context import ContextRef, ContextRole
from agent_platform.domain.context_preparation import RecallIntent


def make_intent(
    *,
    contexts: tuple[ContextRef, ...],
    objective: str = "Write a LinkedIn post about the homelab.",
    step_input: str = "Draft the post.",
) -> RecallIntent:
    return RecallIntent(
        objective=objective,
        step_input=step_input,
        contexts=contexts,
    )


def assert_planner_contract(
    planner: RecallPlannerContract,
) -> None:
    assert planner.name
    assert planner.version


def test_planner_satisfies_recall_planner_contract() -> None:
    assert_planner_contract(DeterministicRecallPlanner())


@pytest.mark.asyncio
async def test_planner_preserves_explicit_context_order() -> None:
    contexts = (
        ContextRef(
            role=ContextRole.SHARED,
            namespace="global",
        ),
        ContextRef(
            role=ContextRole.DELIVERY,
            namespace="app:linkedin",
        ),
        ContextRef(
            role=ContextRole.SUBJECT,
            namespace="project:homelab",
        ),
    )
    planner = DeterministicRecallPlanner()

    plan = await planner.plan(
        make_intent(contexts=contexts),
    )

    assert [request.context for request in plan.requests] == list(contexts)
    assert [request.request_id for request in plan.requests] == [
        "000:shared:global",
        "001:delivery:app:linkedin",
        "002:subject:project:homelab",
    ]


@pytest.mark.asyncio
async def test_planner_uses_objective_and_step_input_in_query() -> None:
    planner = DeterministicRecallPlanner()

    plan = await planner.plan(
        make_intent(
            contexts=(
                ContextRef(
                    role=ContextRole.SUBJECT,
                    namespace="project:homelab",
                ),
            ),
            objective="Explain the homelab.",
            step_input="Draft the architecture section.",
        )
    )

    assert plan.requests[0].query == ("Explain the homelab.\nDraft the architecture section.")


@pytest.mark.asyncio
async def test_planner_is_deterministic_for_fixed_input() -> None:
    intent = make_intent(
        contexts=(
            ContextRef(
                role=ContextRole.DELIVERY,
                namespace="app:linkedin",
            ),
            ContextRef(
                role=ContextRole.SUBJECT,
                namespace="project:homelab",
            ),
        )
    )
    planner = DeterministicRecallPlanner()

    first = await planner.plan(intent)
    second = await planner.plan(intent)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


@pytest.mark.asyncio
async def test_planner_adds_no_implicit_contexts() -> None:
    selected = ContextRef(
        role=ContextRole.SUBJECT,
        namespace="project:homelab",
    )
    planner = DeterministicRecallPlanner()

    plan = await planner.plan(
        make_intent(contexts=(selected,)),
    )

    assert len(plan.requests) == 1
    assert plan.requests[0].context == selected
    assert all(request.context.namespace != "project:agent-platform" for request in plan.requests)
    assert all(request.context.namespace != "global" for request in plan.requests)


@pytest.mark.asyncio
async def test_planner_subject_switch_changes_selected_namespace() -> None:
    planner = DeterministicRecallPlanner()
    homelab = make_intent(
        contexts=(
            ContextRef(
                role=ContextRole.SUBJECT,
                namespace="project:homelab",
            ),
        )
    )
    agent_platform = make_intent(
        contexts=(
            ContextRef(
                role=ContextRole.SUBJECT,
                namespace="project:agent-platform",
            ),
        )
    )

    homelab_plan = await planner.plan(homelab)
    agent_platform_plan = await planner.plan(agent_platform)

    assert homelab_plan.requests[0].context.namespace == ("project:homelab")
    assert agent_platform_plan.requests[0].context.namespace == ("project:agent-platform")


@pytest.mark.asyncio
async def test_no_contexts_produces_empty_plan() -> None:
    planner = DeterministicRecallPlanner()

    plan = await planner.plan(
        make_intent(contexts=()),
    )

    assert plan.requests == ()
    assert plan.planner == "deterministic"
    assert plan.version == "v0"


@pytest.mark.asyncio
async def test_configured_limit_applies_to_every_request() -> None:
    planner = DeterministicRecallPlanner(
        limit_per_context=3,
    )

    plan = await planner.plan(
        make_intent(
            contexts=(
                ContextRef(
                    role=ContextRole.SHARED,
                    namespace="global",
                ),
                ContextRef(
                    role=ContextRole.SUBJECT,
                    namespace="project:homelab",
                ),
            )
        )
    )

    assert [request.limit for request in plan.requests] == [3, 3]


def test_limit_per_context_must_be_positive() -> None:
    with pytest.raises(
        ValueError,
        match="limit_per_context must be greater than 0",
    ):
        DeterministicRecallPlanner(
            limit_per_context=0,
        )
