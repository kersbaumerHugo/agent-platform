from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field

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
from agent_platform.application.context_renderer import (
    MarkdownContextRenderer,
)
from agent_platform.application.context_trace import ContextTraceBuilder
from agent_platform.application.model_gateway import ModelGateway
from agent_platform.application.recall_planner import (
    DeterministicRecallPlanner,
)
from agent_platform.contracts.context import ContextProviderContract
from agent_platform.domain.context import ContextRef
from agent_platform.domain.context_budget import ContextBudget
from agent_platform.domain.context_preparation import RecallIntent
from agent_platform.domain.context_trace import ContextProviderDecision
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
    EvaluationResult,
)
from agent_platform.domain.model import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelResult,
)


class ContextPreparationEvaluationInput(BaseModel):
    objective: str = Field(min_length=1)
    step_input: str = Field(min_length=1)
    contexts: list[ContextRef] = Field(default_factory=list)
    limit_per_context: int = Field(default=5, gt=0)
    budget: ContextBudget
    system_message: str = Field(
        default="Platform system instruction.",
        min_length=1,
    )
    user_message: str = Field(
        default="Complete the task.",
        min_length=1,
    )
    invoke_model: bool = False


class ContextPreparationEvaluationExpected(BaseModel):
    planned_contexts: list[ContextRef] = Field(default_factory=list)
    bundle_contexts: list[ContextRef] = Field(default_factory=list)
    accepted_source_ids: list[str] = Field(default_factory=list)
    provider_decisions: list[ContextProviderDecision] = Field(
        default_factory=list,
    )
    provider_reason_codes: list[str] = Field(default_factory=list)
    retained_item_ids: list[str] = Field(default_factory=list)
    dropped_item_ids: list[str] = Field(default_factory=list)
    rendered_empty: bool
    context_message_count: int = Field(ge=0)
    context_message_role: MessageRole | None = None
    provider_order_invariant: bool = True
    model_call_expected: bool = False
    model_provider: str | None = None
    model_name: str | None = None


class ContextPreparationEvaluator:
    name = "context_preparation"

    def __init__(
        self,
        *,
        provider: ContextProviderContract,
        model_gateway: ModelGateway | None = None,
    ) -> None:
        self._provider = provider
        self._model_gateway = model_gateway

    async def evaluate(
        self,
        case: EvaluationCase,
    ) -> EvaluationResult:
        evaluation_input = ContextPreparationEvaluationInput.model_validate(
            case.input,
        )
        expected = ContextPreparationEvaluationExpected.model_validate(
            case.expected,
        )

        planner = DeterministicRecallPlanner(
            limit_per_context=evaluation_input.limit_per_context,
        )
        assembler = DeterministicContextAssembler()
        estimator = Utf8ByteTokenEstimator()
        budget_policy = DeterministicContextBudgetPolicy(
            estimator=estimator,
        )
        renderer = MarkdownContextRenderer()
        injector = ReferenceMessageInjector()
        trace_builder = ContextTraceBuilder()

        plan = await planner.plan(
            RecallIntent(
                objective=evaluation_input.objective,
                step_input=evaluation_input.step_input,
                contexts=tuple(evaluation_input.contexts),
            )
        )

        provider_results = [await self._provider.provide(request) for request in plan.requests]
        contributions = [result.contribution for result in provider_results]

        bundle = assembler.assemble(contributions)
        reversed_bundle = assembler.assemble(
            tuple(reversed(contributions)),
        )

        budgeted = budget_policy.apply(
            bundle,
            evaluation_input.budget,
        )
        reversed_budgeted = budget_policy.apply(
            reversed_bundle,
            evaluation_input.budget,
        )

        rendered = renderer.render(budgeted)
        reversed_rendered = renderer.render(reversed_budgeted)

        base_request = ModelRequest(
            run_id=uuid5(
                NAMESPACE_URL,
                f"agent-platform:m10-eval:{case.case_id}",
            ),
            messages=[
                ModelMessage(
                    role=MessageRole.SYSTEM,
                    content=evaluation_input.system_message,
                ),
                ModelMessage(
                    role=MessageRole.USER,
                    content=evaluation_input.user_message,
                ),
            ],
            max_tokens=(
                evaluation_input.budget.reserved_output_tokens
                if evaluation_input.budget.reserved_output_tokens > 0
                else None
            ),
        )

        injected = injector.inject(
            base_request,
            rendered,
        )

        trace = trace_builder.build(
            plan=plan,
            provider_results=provider_results,
            assembler_version=assembler.version,
            budget_policy_version=budget_policy.version,
            token_estimator_version=estimator.version,
            budgeted=budgeted,
            rendered=rendered,
            injector_name=injector.name,
            injector_version=injector.version,
        )

        model_result: ModelResult | None = None
        if evaluation_input.invoke_model:
            if self._model_gateway is None:
                raise ValueError(
                    "ContextPreparationEvaluator requires a model gateway "
                    "when invoke_model is true."
                )
            model_result = await self._model_gateway.generate(injected)

        actual_planned_contexts = [request.context for request in plan.requests]
        actual_bundle_contexts = [section.context for section in bundle.sections]
        actual_accepted_source_ids = [
            source.source_id
            for result in provider_results
            for source in result.trace.accepted_sources
        ]
        actual_provider_decisions = [result.trace.decision for result in provider_results]
        actual_provider_reason_codes = [result.trace.reason_code for result in provider_results]
        actual_retained_item_ids = [
            item.item_id for section in budgeted.bundle.sections for item in section.items
        ]
        actual_dropped_item_ids = list(
            budgeted.dropped_item_ids,
        )

        context_messages = (
            [
                message
                for message in injected.messages
                if rendered.text and message.content == rendered.text
            ]
            if rendered.text
            else []
        )
        actual_context_message_role = (
            context_messages[0].role if len(context_messages) == 1 else None
        )

        original_system_messages = [
            message for message in base_request.messages if message.role is MessageRole.SYSTEM
        ]
        injected_system_messages = [
            message for message in injected.messages if message.role is MessageRole.SYSTEM
        ]

        provider_order_invariant = reversed_bundle == bundle
        rendered_hash_order_invariant = reversed_rendered.content_hash == rendered.content_hash
        budget_within_limit = budgeted.estimated_tokens <= budgeted.budget_tokens
        trace_consistent = (
            trace.rendering.content_hash == rendered.content_hash
            and [
                source.source_id
                for provider_trace in trace.provider_traces
                for source in provider_trace.accepted_sources
            ]
            == actual_accepted_source_ids
            and trace.budget.dropped_item_ids == budgeted.dropped_item_ids
        )

        model_call_actual = model_result is not None
        model_identity_match = (
            expected.model_provider is None and expected.model_name is None and model_result is None
        ) or (
            model_result is not None
            and model_result.provider == expected.model_provider
            and model_result.model == expected.model_name
        )

        checks = {
            "planned_contexts_match": (actual_planned_contexts == expected.planned_contexts),
            "bundle_contexts_match": (actual_bundle_contexts == expected.bundle_contexts),
            "accepted_source_ids_match": (
                actual_accepted_source_ids == expected.accepted_source_ids
            ),
            "provider_decisions_match": (actual_provider_decisions == expected.provider_decisions),
            "provider_reason_codes_match": (
                actual_provider_reason_codes == expected.provider_reason_codes
            ),
            "retained_item_ids_match": (actual_retained_item_ids == expected.retained_item_ids),
            "dropped_item_ids_match": (actual_dropped_item_ids == expected.dropped_item_ids),
            "rendered_empty_match": ((rendered.text == "") is expected.rendered_empty),
            "context_message_count_match": (
                len(context_messages) == expected.context_message_count
            ),
            "context_message_role_match": (
                actual_context_message_role is expected.context_message_role
            ),
            "system_messages_unchanged": (injected_system_messages == original_system_messages),
            "provider_order_invariant": (
                provider_order_invariant is expected.provider_order_invariant
            ),
            "rendered_hash_order_invariant": (rendered_hash_order_invariant),
            "budget_within_limit": (budget_within_limit),
            "trace_consistent": (trace_consistent),
            "model_call_match": (model_call_actual is expected.model_call_expected),
            "model_identity_match": (model_identity_match),
        }
        expectations_met = all(checks.values())

        return EvaluationResult(
            case_id=case.case_id,
            evaluator=self.name,
            outcome=(EvaluationOutcome.PASS if expectations_met else EvaluationOutcome.FAIL),
            reason_code=("expectations_met" if expectations_met else "expectation_mismatch"),
            metrics={key: float(value) for key, value in checks.items()},
            metadata={
                "actual_planned_contexts": [
                    context.model_dump(mode="json") for context in actual_planned_contexts
                ],
                "actual_bundle_contexts": [
                    context.model_dump(mode="json") for context in actual_bundle_contexts
                ],
                "accepted_source_ids": (actual_accepted_source_ids),
                "provider_decisions": [decision.value for decision in actual_provider_decisions],
                "provider_reason_codes": (actual_provider_reason_codes),
                "retained_item_ids": (actual_retained_item_ids),
                "dropped_item_ids": (actual_dropped_item_ids),
                "budget_tokens": budgeted.budget_tokens,
                "estimated_tokens": (budgeted.estimated_tokens),
                "rendered_context_hash": (rendered.content_hash),
                "context_message_count": len(
                    context_messages,
                ),
                "context_message_role": (
                    actual_context_message_role.value
                    if actual_context_message_role is not None
                    else None
                ),
                "system_message_count": len(
                    injected_system_messages,
                ),
                "provider_order_invariant": (provider_order_invariant),
                "rendered_hash_order_invariant": (rendered_hash_order_invariant),
                "model_provider": (model_result.provider if model_result is not None else None),
                "model_name": (model_result.model if model_result is not None else None),
                "trace": trace.model_dump(mode="json"),
            },
        )
