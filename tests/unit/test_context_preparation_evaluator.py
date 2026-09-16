import pytest

from agent_platform.adapters.evaluation.context_preparation import (
    ContextPreparationEvaluator,
)
from agent_platform.application.model_gateway import ModelGateway
from agent_platform.domain.context import (
    ContextContribution,
    ContextItem,
    ContextProvenance,
    ContextRef,
    ContextRole,
    content_sha256,
)
from agent_platform.domain.context_preparation import RecallRequest
from agent_platform.domain.context_trace import (
    ContextProviderDecision,
    ContextProviderResult,
    ContextProviderTrace,
    ContextSourceEvidence,
)
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
)
from agent_platform.domain.model import (
    MessageRole,
    ModelRequest,
    ModelResult,
)
from agent_platform.domain.observability import ObservationEvent


class StaticProvider:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def name(self) -> str:
        return "static"

    async def provide(
        self,
        request: RecallRequest,
    ) -> ContextProviderResult:
        self.calls += 1
        content = "RAW SECRET CONTEXT"
        source_id = request.context.namespace
        item = ContextItem(
            item_id=f"static:{source_id}",
            content=content,
            kind="fact",
            context=request.context,
            provenance=ContextProvenance(
                provider=self.name,
                source_id=source_id,
                content_hash=content_sha256(content),
            ),
        )
        contribution = ContextContribution(
            provider=self.name,
            context=request.context,
            items=(item,),
        )
        return ContextProviderResult(
            contribution=contribution,
            trace=ContextProviderTrace(
                request_id=request.request_id,
                provider=self.name,
                context=request.context,
                decision=ContextProviderDecision.ACCEPT,
                reason_code="static_evidence",
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


class RecordingModel:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    @property
    def provider(self) -> str:
        return "test-provider"

    @property
    def model(self) -> str:
        return "test-model"

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        self.requests.append(request)
        return ModelResult(
            provider=self.provider,
            model=self.model,
            output="ok",
        )


class NoopObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


def subject_context() -> ContextRef:
    return ContextRef(
        role=ContextRole.SUBJECT,
        namespace="project:test",
    )


def passing_case(
    *,
    invoke_model: bool = False,
    model_provider: str | None = None,
    model_name: str | None = None,
) -> EvaluationCase:
    context = subject_context()
    return EvaluationCase(
        case_id="case",
        input={
            "objective": "do",
            "step_input": "work",
            "contexts": [
                context.model_dump(mode="json"),
            ],
            "budget": {
                "max_total_tokens": 100,
            },
            "invoke_model": invoke_model,
        },
        expected={
            "planned_contexts": [
                context.model_dump(mode="json"),
            ],
            "bundle_contexts": [
                context.model_dump(mode="json"),
            ],
            "accepted_source_ids": [
                context.namespace,
            ],
            "provider_decisions": [
                "accept",
            ],
            "provider_reason_codes": [
                "static_evidence",
            ],
            "retained_item_ids": [
                f"static:{context.namespace}",
            ],
            "dropped_item_ids": [],
            "rendered_empty": False,
            "context_message_count": 1,
            "context_message_role": "user",
            "provider_order_invariant": True,
            "model_call_expected": invoke_model,
            "model_provider": model_provider,
            "model_name": model_name,
        },
    )


@pytest.mark.asyncio
async def test_evaluator_passes_fixed_context_preparation_case() -> None:
    evaluator = ContextPreparationEvaluator(
        provider=StaticProvider(),
    )

    result = await evaluator.evaluate(
        passing_case(),
    )

    assert result.outcome is EvaluationOutcome.PASS
    assert result.reason_code == "expectations_met"
    assert result.metrics["trace_consistent"] == 1.0
    assert result.metrics["system_messages_unchanged"] == 1.0


@pytest.mark.asyncio
async def test_evaluator_metadata_excludes_raw_context() -> None:
    evaluator = ContextPreparationEvaluator(
        provider=StaticProvider(),
    )

    result = await evaluator.evaluate(
        passing_case(),
    )

    serialized = result.model_dump_json()
    assert "RAW SECRET CONTEXT" not in serialized
    assert "sha256:" in serialized
    assert "project:test" in serialized


@pytest.mark.asyncio
async def test_evaluator_reports_expectation_mismatch() -> None:
    case = passing_case()
    case.expected["accepted_source_ids"] = [
        "wrong-source",
    ]
    evaluator = ContextPreparationEvaluator(
        provider=StaticProvider(),
    )

    result = await evaluator.evaluate(case)

    assert result.outcome is EvaluationOutcome.FAIL
    assert result.reason_code == "expectation_mismatch"
    assert result.metrics["accepted_source_ids_match"] == 0.0


@pytest.mark.asyncio
async def test_no_selected_context_skips_provider() -> None:
    provider = StaticProvider()
    evaluator = ContextPreparationEvaluator(
        provider=provider,
    )
    case = EvaluationCase(
        case_id="empty",
        input={
            "objective": "do",
            "step_input": "work",
            "contexts": [],
            "budget": {
                "max_total_tokens": 100,
            },
        },
        expected={
            "planned_contexts": [],
            "bundle_contexts": [],
            "accepted_source_ids": [],
            "provider_decisions": [],
            "provider_reason_codes": [],
            "retained_item_ids": [],
            "dropped_item_ids": [],
            "rendered_empty": True,
            "context_message_count": 0,
            "context_message_role": None,
            "provider_order_invariant": True,
            "model_call_expected": False,
        },
    )

    result = await evaluator.evaluate(case)

    assert result.outcome is EvaluationOutcome.PASS
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_model_independence_uses_canonical_model_request() -> None:
    model = RecordingModel()
    gateway = ModelGateway(
        model=model,
        observer=NoopObserver(),
    )
    evaluator = ContextPreparationEvaluator(
        provider=StaticProvider(),
        model_gateway=gateway,
    )

    result = await evaluator.evaluate(
        passing_case(
            invoke_model=True,
            model_provider="test-provider",
            model_name="test-model",
        )
    )

    assert result.outcome is EvaluationOutcome.PASS
    assert len(model.requests) == 1

    request = model.requests[0]
    assert isinstance(request, ModelRequest)
    assert [message.role for message in request.messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.USER,
    ]


@pytest.mark.asyncio
async def test_model_invocation_without_gateway_fails_closed() -> None:
    evaluator = ContextPreparationEvaluator(
        provider=StaticProvider(),
    )

    with pytest.raises(
        ValueError,
        match="requires a model gateway",
    ):
        await evaluator.evaluate(
            passing_case(
                invoke_model=True,
                model_provider="missing",
                model_name="missing",
            )
        )
