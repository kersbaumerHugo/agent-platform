import pytest
from pydantic import ValidationError

from agent_platform.application.context_trace import ContextTraceBuilder
from agent_platform.domain.context import (
    ContextBundle,
    ContextContribution,
    ContextItem,
    ContextProvenance,
    ContextRef,
    ContextRole,
    content_sha256,
)
from agent_platform.domain.context_budget import BudgetedContextBundle
from agent_platform.domain.context_preparation import RecallPlan, RecallRequest
from agent_platform.domain.context_rendering import RenderedContext
from agent_platform.domain.context_trace import (
    ContextProviderDecision,
    ContextProviderResult,
    ContextProviderTrace,
    ContextSourceEvidence,
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


def make_plan() -> RecallPlan:
    return RecallPlan(
        planner="deterministic",
        version="v0",
        requests=(
            RecallRequest(
                request_id="001:shared:global",
                context=make_context(
                    role=ContextRole.SHARED,
                    namespace="global",
                ),
                query="shared query that must not enter trace",
            ),
            RecallRequest(
                request_id="002:subject:project:homelab",
                context=make_context(),
                query="homelab secret query that must not enter trace",
            ),
        ),
    )


def make_provider_result(
    *,
    request_id: str,
    context: ContextRef,
    provider: str = "memory",
    source_id: str = "source-1",
    content: str = "SUPER SECRET RAW CONTENT",
) -> ContextProviderResult:
    item = ContextItem(
        item_id=f"{provider}:{source_id}",
        content=content,
        kind="fact",
        context=context,
        provenance=ContextProvenance(
            provider=provider,
            source_id=source_id,
            content_hash=content_sha256(content),
        ),
    )
    contribution = ContextContribution(
        provider=provider,
        context=context,
        items=(item,),
    )
    trace = ContextProviderTrace(
        request_id=request_id,
        provider=provider,
        context=context,
        decision=ContextProviderDecision.ACCEPT,
        reason_code="accepted",
        candidate_count=1,
        accepted_count=1,
        rejected_count=0,
        accepted_sources=(
            ContextSourceEvidence(
                source_id=source_id,
                content_hash=item.provenance.content_hash,
            ),
        ),
    )
    return ContextProviderResult(
        contribution=contribution,
        trace=trace,
    )


def make_abstain_result(
    *,
    request_id: str,
    context: ContextRef,
    provider: str = "memory",
) -> ContextProviderResult:
    return ContextProviderResult(
        contribution=ContextContribution(
            provider=provider,
            context=context,
        ),
        trace=ContextProviderTrace(
            request_id=request_id,
            provider=provider,
            context=context,
            decision=ContextProviderDecision.ABSTAIN,
            reason_code="insufficient_term_coverage",
            candidate_count=2,
            accepted_count=0,
            rejected_count=2,
        ),
    )


def make_budgeted() -> BudgetedContextBundle:
    return BudgetedContextBundle(
        bundle=ContextBundle(),
        budget_tokens=128,
        estimated_tokens=64,
        dropped_item_ids=("memory:dropped-1",),
    )


def make_rendered() -> RenderedContext:
    text = "safe rendered context"
    return RenderedContext(
        renderer="markdown",
        version="v0",
        text=text,
        content_hash=content_sha256(text),
    )


def build_trace(
    *,
    plan: RecallPlan | None = None,
    provider_results: tuple[ContextProviderResult, ...] | None = None,
):
    selected_plan = plan or make_plan()
    if provider_results is None:
        provider_results = tuple(
            make_provider_result(
                request_id=request.request_id,
                context=request.context,
                source_id=f"source-{index}",
            )
            for index, request in enumerate(
                selected_plan.requests,
                start=1,
            )
        )

    return ContextTraceBuilder().build(
        plan=selected_plan,
        provider_results=provider_results,
        assembler_version="v0",
        budget_policy_version="canonical-prefix-v0",
        token_estimator_version="utf8-bytes-v0",
        budgeted=make_budgeted(),
        rendered=make_rendered(),
        injector_name="reference-message",
        injector_version="v0",
    )


def test_provider_result_rejects_trace_provenance_divergence() -> None:
    context = make_context()
    item = ContextItem(
        item_id="memory:source-1",
        content="content",
        kind="fact",
        context=context,
        provenance=ContextProvenance(
            provider="memory",
            source_id="source-1",
            content_hash=content_sha256("content"),
        ),
    )

    with pytest.raises(
        ValidationError,
        match="accepted_sources must match contribution provenance",
    ):
        ContextProviderResult(
            contribution=ContextContribution(
                provider="memory",
                context=context,
                items=(item,),
            ),
            trace=ContextProviderTrace(
                request_id="subject",
                provider="memory",
                context=context,
                decision=ContextProviderDecision.ACCEPT,
                reason_code="accepted",
                candidate_count=1,
                accepted_count=1,
                rejected_count=0,
                accepted_sources=(
                    ContextSourceEvidence(
                        source_id="different-source",
                        content_hash=content_sha256("content"),
                    ),
                ),
            ),
        )


def test_builder_uses_plan_order_and_canonical_provider_order() -> None:
    plan = make_plan()
    shared_request, subject_request = plan.requests

    results = (
        make_provider_result(
            request_id=subject_request.request_id,
            context=subject_request.context,
            provider="workspace",
            source_id="workspace-subject",
        ),
        make_provider_result(
            request_id=shared_request.request_id,
            context=shared_request.context,
            provider="memory",
            source_id="memory-shared",
        ),
        make_provider_result(
            request_id=subject_request.request_id,
            context=subject_request.context,
            provider="memory",
            source_id="memory-subject",
        ),
    )

    trace = build_trace(
        plan=plan,
        provider_results=results,
    )

    assert [(provider.request_id, provider.provider) for provider in trace.provider_traces] == [
        ("001:shared:global", "memory"),
        ("002:subject:project:homelab", "memory"),
        ("002:subject:project:homelab", "workspace"),
    ]


def test_trace_contains_versions_budget_and_rendered_hash() -> None:
    trace = build_trace()

    assert trace.version == "v0"
    assert trace.planner == "deterministic"
    assert trace.planner_version == "v0"
    assert trace.assembler_version == "v0"
    assert trace.budget.policy_version == "canonical-prefix-v0"
    assert trace.budget.estimator_version == "utf8-bytes-v0"
    assert trace.budget.budget_tokens == 128
    assert trace.budget.estimated_tokens == 64
    assert trace.budget.dropped_item_ids == ("memory:dropped-1",)
    assert trace.rendering.renderer == "markdown"
    assert trace.rendering.version == "v0"
    assert trace.rendering.content_hash == make_rendered().content_hash
    assert trace.injection.injector == "reference-message"
    assert trace.injection.version == "v0"


def test_trace_excludes_raw_context_and_recall_query_text() -> None:
    trace = build_trace()
    serialized = trace.model_dump_json()

    assert "SUPER SECRET RAW CONTENT" not in serialized
    assert "shared query that must not enter trace" not in serialized
    assert "homelab secret query that must not enter trace" not in serialized
    assert "source-1" in serialized
    assert "sha256:" in serialized


def test_abstention_reason_and_counts_survive_trace() -> None:
    plan = RecallPlan(
        planner="deterministic",
        version="v0",
        requests=(
            RecallRequest(
                request_id="subject",
                context=make_context(),
                query="query",
            ),
        ),
    )

    trace = build_trace(
        plan=plan,
        provider_results=(
            make_abstain_result(
                request_id="subject",
                context=plan.requests[0].context,
            ),
        ),
    )

    provider = trace.provider_traces[0]
    assert provider.decision is ContextProviderDecision.ABSTAIN
    assert provider.reason_code == "insufficient_term_coverage"
    assert provider.candidate_count == 2
    assert provider.accepted_count == 0
    assert provider.rejected_count == 2
    assert provider.accepted_sources == ()


def test_unknown_provider_result_request_fails_closed() -> None:
    plan = make_plan()

    with pytest.raises(
        ValueError,
        match="unknown request_id",
    ):
        build_trace(
            plan=plan,
            provider_results=(
                make_provider_result(
                    request_id="unknown",
                    context=plan.requests[0].context,
                ),
            ),
        )


def test_missing_provider_result_fails_closed() -> None:
    plan = make_plan()

    with pytest.raises(
        ValueError,
        match="at least one provider result",
    ):
        build_trace(
            plan=plan,
            provider_results=(
                make_provider_result(
                    request_id=plan.requests[0].request_id,
                    context=plan.requests[0].context,
                ),
            ),
        )


def test_provider_context_mismatch_fails_closed() -> None:
    plan = make_plan()
    first, second = plan.requests

    with pytest.raises(
        ValueError,
        match="context must match RecallPlan",
    ):
        build_trace(
            plan=plan,
            provider_results=(
                make_provider_result(
                    request_id=first.request_id,
                    context=second.context,
                ),
                make_provider_result(
                    request_id=second.request_id,
                    context=second.context,
                ),
            ),
        )


def test_duplicate_provider_result_fails_closed() -> None:
    plan = RecallPlan(
        planner="deterministic",
        version="v0",
        requests=(
            RecallRequest(
                request_id="subject",
                context=make_context(),
                query="query",
            ),
        ),
    )
    result = make_provider_result(
        request_id="subject",
        context=plan.requests[0].context,
    )

    with pytest.raises(
        ValueError,
        match="duplicate provider results",
    ):
        build_trace(
            plan=plan,
            provider_results=(
                result,
                result.model_copy(deep=True),
            ),
        )


def test_trace_serialization_is_deterministic() -> None:
    first = build_trace()
    second = build_trace()

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
