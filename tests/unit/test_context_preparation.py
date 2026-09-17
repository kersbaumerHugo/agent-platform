import pytest
from pydantic import ValidationError

from agent_platform.application.context_assembler import (
    DeterministicContextAssembler,
)
from agent_platform.application.context_budget import (
    DeterministicContextBudgetPolicy,
    Utf8ByteTokenEstimator,
)
from agent_platform.application.context_injector import (
    ReferenceMessageInjector,
)
from agent_platform.application.context_preparation import PrepareContext
from agent_platform.application.context_renderer import (
    MarkdownContextRenderer,
)
from agent_platform.application.context_trace import ContextTraceBuilder
from agent_platform.application.recall_planner import (
    DeterministicRecallPlanner,
)
from agent_platform.domain.context import (
    ContextContribution,
    ContextItem,
    ContextProvenance,
    ContextRef,
    ContextRole,
    content_sha256,
)
from agent_platform.domain.context_budget import ContextBudget
from agent_platform.domain.context_preparation import (
    ContextPreparationResult,
    RecallRequest,
)
from agent_platform.domain.context_rendering import RenderedContext
from agent_platform.domain.context_trace import (
    ContextProviderDecision,
    ContextProviderResult,
    ContextProviderTrace,
    ContextSourceEvidence,
)


class RecordingProvider:
    def __init__(
        self,
        *,
        decision: ContextProviderDecision = ContextProviderDecision.ACCEPT,
        reason_code: str = "accepted",
    ) -> None:
        self._decision = decision
        self._reason_code = reason_code
        self.requests: list[RecallRequest] = []

    @property
    def name(self) -> str:
        return "recording"

    async def provide(
        self,
        request: RecallRequest,
    ) -> ContextProviderResult:
        self.requests.append(request)

        if self._decision is ContextProviderDecision.ABSTAIN:
            return ContextProviderResult(
                contribution=ContextContribution(
                    provider=self.name,
                    context=request.context,
                ),
                trace=ContextProviderTrace(
                    request_id=request.request_id,
                    provider=self.name,
                    context=request.context,
                    decision=self._decision,
                    reason_code=self._reason_code,
                    candidate_count=1,
                    accepted_count=0,
                    rejected_count=1,
                ),
            )

        content = f"reference for {request.context.namespace}: {request.query}"
        source_id = f"source:{request.context.namespace}"
        item = ContextItem(
            item_id=f"{self.name}:{request.context.namespace}",
            content=content,
            kind="fact",
            context=request.context,
            provenance=ContextProvenance(
                provider=self.name,
                source_id=source_id,
                content_hash=content_sha256(content),
            ),
        )

        return ContextProviderResult(
            contribution=ContextContribution(
                provider=self.name,
                context=request.context,
                items=(item,),
            ),
            trace=ContextProviderTrace(
                request_id=request.request_id,
                provider=self.name,
                context=request.context,
                decision=self._decision,
                reason_code=self._reason_code,
                candidate_count=1,
                accepted_count=1,
                rejected_count=0,
                accepted_sources=(
                    ContextSourceEvidence(
                        source_id=source_id,
                        content_hash=item.provenance.content_hash,
                    ),
                ),
            ),
        )


def make_context() -> ContextRef:
    return ContextRef(
        role=ContextRole.SUBJECT,
        namespace="project:homelab",
    )


def make_service(
    provider: RecordingProvider,
) -> PrepareContext:
    estimator = Utf8ByteTokenEstimator()

    return PrepareContext(
        planner=DeterministicRecallPlanner(),
        provider=provider,
        assembler=DeterministicContextAssembler(),
        budget_policy=DeterministicContextBudgetPolicy(
            estimator=estimator,
        ),
        token_estimator=estimator,
        renderer=MarkdownContextRenderer(),
        injector=ReferenceMessageInjector(),
        trace_builder=ContextTraceBuilder(),
    )


@pytest.mark.asyncio
async def test_prepare_context_returns_execution_ready_result() -> None:
    provider = RecordingProvider()
    service = make_service(provider)

    result = await service.execute(
        objective="Write about the homelab.",
        step_input="Draft the post.",
        contexts=(make_context(),),
        budget=ContextBudget(
            max_total_tokens=256,
            reserved_output_tokens=32,
        ),
    )

    assert isinstance(result, ContextPreparationResult)
    assert result.rendered.text
    assert "project:homelab" in result.rendered.text
    assert "reference for project:homelab" in result.rendered.text
    assert result.trace.rendering.content_hash == result.rendered.content_hash
    assert result.trace.planner == "deterministic"
    assert result.trace.assembler_version == "v0"
    assert result.trace.budget.policy_version == "canonical-prefix-v0"
    assert result.trace.budget.estimator_version == "utf8-bytes-v0"
    assert result.trace.injection.injector == "reference-message"


@pytest.mark.asyncio
async def test_same_input_produces_same_preparation_result() -> None:
    provider = RecordingProvider()
    service = make_service(provider)
    kwargs = {
        "objective": "Write about the homelab.",
        "step_input": "Draft the post.",
        "contexts": (make_context(),),
        "budget": ContextBudget(max_total_tokens=256),
    }

    first = await service.execute(**kwargs)
    second = await service.execute(**kwargs)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


@pytest.mark.asyncio
async def test_no_context_skips_provider_and_renders_empty() -> None:
    provider = RecordingProvider()
    service = make_service(provider)

    result = await service.execute(
        objective="Do the work.",
        step_input="Execute.",
        contexts=(),
        budget=ContextBudget(max_total_tokens=128),
    )

    assert provider.requests == []
    assert result.rendered.text == ""
    assert result.trace.provider_traces == ()
    assert result.trace.rendering.content_hash == content_sha256("")


@pytest.mark.asyncio
async def test_abstain_contributes_no_rendered_content() -> None:
    provider = RecordingProvider(
        decision=ContextProviderDecision.ABSTAIN,
        reason_code="insufficient_evidence",
    )
    service = make_service(provider)

    result = await service.execute(
        objective="Write about the homelab.",
        step_input="Draft the post.",
        contexts=(make_context(),),
        budget=ContextBudget(max_total_tokens=128),
    )

    assert result.rendered.text == ""
    assert len(result.trace.provider_traces) == 1
    provider_trace = result.trace.provider_traces[0]
    assert provider_trace.decision is ContextProviderDecision.ABSTAIN
    assert provider_trace.reason_code == "insufficient_evidence"
    assert provider_trace.accepted_sources == ()


@pytest.mark.asyncio
async def test_preparation_is_step_aware() -> None:
    provider = RecordingProvider()
    service = make_service(provider)

    await service.execute(
        objective="Publish the homelab update.",
        step_input="Draft the opening.",
        contexts=(make_context(),),
        budget=ContextBudget(max_total_tokens=256),
    )
    await service.execute(
        objective="Publish the homelab update.",
        step_input="Draft the conclusion.",
        contexts=(make_context(),),
        budget=ContextBudget(max_total_tokens=256),
    )

    assert provider.requests[0].query == ("Publish the homelab update.\nDraft the opening.")
    assert provider.requests[1].query == ("Publish the homelab update.\nDraft the conclusion.")


@pytest.mark.asyncio
async def test_result_rejects_rendered_trace_divergence() -> None:
    provider = RecordingProvider()
    service = make_service(provider)

    result = await service.execute(
        objective="Write about the homelab.",
        step_input="Draft the post.",
        contexts=(make_context(),),
        budget=ContextBudget(max_total_tokens=256),
    )

    different_text = "different rendered context"
    different_rendered = RenderedContext(
        renderer="markdown",
        version="v0",
        text=different_text,
        content_hash=content_sha256(different_text),
    )

    with pytest.raises(
        ValidationError,
        match="must match rendered context",
    ):
        ContextPreparationResult(
            rendered=different_rendered,
            trace=result.trace,
        )
