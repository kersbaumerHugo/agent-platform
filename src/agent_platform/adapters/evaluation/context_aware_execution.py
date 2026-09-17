import asyncio
from enum import StrEnum
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException
from pydantic import BaseModel

from agent_platform.api.openai_compat import inject_bound_context
from agent_platform.application.context_assembler import (
    DeterministicContextAssembler,
)
from agent_platform.application.context_budget import (
    DeterministicContextBudgetPolicy,
    Utf8ByteTokenEstimator,
)
from agent_platform.application.context_injector import ReferenceMessageInjector
from agent_platform.application.context_preparation import PrepareContext
from agent_platform.application.context_renderer import MarkdownContextRenderer
from agent_platform.application.context_trace import ContextTraceBuilder
from agent_platform.application.model_gateway import ModelGateway
from agent_platform.application.recall_planner import DeterministicRecallPlanner
from agent_platform.application.run_agent import RunAgent
from agent_platform.application.run_context import InMemoryRunContextBindings
from agent_platform.application.work_orchestrator import WorkOrchestrator
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
from agent_platform.domain.context_trace import (
    ContextProviderDecision,
    ContextProviderResult,
    ContextProviderTrace,
    ContextSourceEvidence,
)
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
from agent_platform.domain.models import RuntimeRequest, RuntimeResult
from agent_platform.domain.observability import ObservationEvent
from agent_platform.domain.work import WorkRequest, WorkStatus


class ContextAwareExecutionScenario(StrEnum):
    WORK = "work"
    MISSING_BINDING = "missing_binding"
    MULTI_TURN = "multi_turn"
    CONCURRENT_ISOLATION = "concurrent_isolation"
    RUNTIME_PROVIDER_INDEPENDENCE = "runtime_provider_independence"


class ContextAwareExecutionEvaluationInput(BaseModel):
    scenario: ContextAwareExecutionScenario
    work: WorkRequest | None = None
    runtime_failure_input: str | None = None


class ContextAwareExecutionEvaluationExpected(BaseModel):
    work_status: WorkStatus | None = None
    executed_step_ids: list[str] | None = None
    run_statuses: list[str] | None = None
    work_contexts: list[ContextRef] | None = None
    trace_present: list[bool] | None = None
    traced_contexts: list[list[ContextRef]] | None = None
    bindings_cleared: bool | None = None
    runtime_context_present: list[bool] | None = None
    runtime_required: list[bool] | None = None
    distinct_run_ids: bool | None = None
    gateway_status_code: int | None = None
    gateway_error_type: str | None = None
    context_message_counts: list[int] | None = None
    context_message_role: MessageRole | None = None
    system_messages_unchanged: bool | None = None
    binding_retained: bool | None = None
    isolated: bool | None = None
    equivalent_across_runtimes: bool | None = None
    provider_neutral: bool | None = None


class _DeterministicContextProvider:
    name = "m11-eval-context"

    async def provide(
        self,
        request: RecallRequest,
    ) -> ContextProviderResult:
        content = (
            f"context={request.context.role.value}:{request.context.namespace}\n"
            f"query={request.query}"
        )
        content_hash = content_sha256(content)
        source_id = f"m11-eval:{request.context.role.value}:{request.context.namespace}"
        item = ContextItem(
            item_id=source_id,
            content=content,
            kind="evaluation",
            context=request.context,
            provenance=ContextProvenance(
                provider=self.name,
                source_id=source_id,
                source_revision="v0",
                content_hash=content_hash,
            ),
        )
        contribution = ContextContribution(
            provider=self.name,
            context=request.context,
            items=(item,),
        )
        trace = ContextProviderTrace(
            request_id=request.request_id,
            provider=self.name,
            context=request.context,
            decision=ContextProviderDecision.ACCEPT,
            reason_code="eval_accept",
            candidate_count=1,
            accepted_count=1,
            rejected_count=0,
            accepted_sources=(
                ContextSourceEvidence(
                    source_id=source_id,
                    content_hash=content_hash,
                ),
            ),
        )
        return ContextProviderResult(
            contribution=contribution,
            trace=trace,
        )


class _NoopObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


class _EvaluationRuntime:
    def __init__(
        self,
        *,
        bindings: InMemoryRunContextBindings,
        name: str,
        fail_on_input: str | None = None,
    ) -> None:
        self._bindings = bindings
        self._name = name
        self._fail_on_input = fail_on_input
        self.run_ids: list[UUID] = []
        self.context_present: list[bool] = []
        self.required: list[bool] = []

    @property
    def name(self) -> str:
        return self._name

    async def execute(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResult:
        prepared = self._bindings.resolve(request.run_id)

        self.run_ids.append(request.run_id)
        self.context_present.append(prepared is not None)
        self.required.append(self._bindings.is_required(request.run_id))

        if request.input == self._fail_on_input:
            raise RuntimeError("planned M11 evaluation runtime failure")

        return RuntimeResult(
            output=f"completed:{request.agent_id}:{request.input}",
        )


class _CapturingModel:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
    ) -> None:
        self._provider = provider
        self._model = model
        self.requests: list[ModelRequest] = []

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        self.requests.append(request)
        return ModelResult(
            provider=self.provider,
            model=self.model,
            output="ok",
            finish_reason="stop",
        )


class ContextAwareExecutionEvaluator:
    name = "context_aware_work_execution"

    async def evaluate(
        self,
        case: EvaluationCase,
    ) -> EvaluationResult:
        evaluation_input = ContextAwareExecutionEvaluationInput.model_validate(case.input)
        expected = ContextAwareExecutionEvaluationExpected.model_validate(case.expected)

        if evaluation_input.scenario is ContextAwareExecutionScenario.WORK:
            facts = await self._evaluate_work(evaluation_input)
        elif evaluation_input.scenario is ContextAwareExecutionScenario.MISSING_BINDING:
            facts = await self._evaluate_missing_binding(case)
        elif evaluation_input.scenario is ContextAwareExecutionScenario.MULTI_TURN:
            facts = await self._evaluate_multi_turn(case)
        elif evaluation_input.scenario is ContextAwareExecutionScenario.CONCURRENT_ISOLATION:
            facts = await self._evaluate_concurrent_isolation(case)
        else:
            facts = await self._evaluate_runtime_provider_independence(
                case,
                evaluation_input,
            )

        expected_values = expected.model_dump(
            mode="json",
            exclude_none=True,
        )
        checks = {key: facts.get(key) == value for key, value in expected_values.items()}
        expectations_met = all(checks.values())

        return EvaluationResult(
            case_id=case.case_id,
            evaluator=self.name,
            outcome=(EvaluationOutcome.PASS if expectations_met else EvaluationOutcome.FAIL),
            reason_code=("expectations_met" if expectations_met else "expectation_mismatch"),
            metrics={f"{key}_match": float(value) for key, value in checks.items()},
            metadata={
                "scenario": evaluation_input.scenario.value,
                "facts": facts,
            },
        )

    async def _evaluate_work(
        self,
        evaluation_input: ContextAwareExecutionEvaluationInput,
    ) -> dict[str, Any]:
        if evaluation_input.work is None:
            raise ValueError("work is required for the work evaluation scenario.")

        return await self._execute_work(
            evaluation_input.work,
            runtime_name="m11-eval-runtime",
            fail_on_input=evaluation_input.runtime_failure_input,
        )

    async def _execute_work(
        self,
        work: WorkRequest,
        *,
        runtime_name: str,
        fail_on_input: str | None = None,
    ) -> dict[str, Any]:
        bindings = InMemoryRunContextBindings()
        runtime = _EvaluationRuntime(
            bindings=bindings,
            name=runtime_name,
            fail_on_input=fail_on_input,
        )
        orchestrator = WorkOrchestrator(
            RunAgent(
                runtime=runtime,
                observer=_NoopObserver(),
                run_context_bindings=bindings,
            ),
            prepare_context=self._build_prepare_context(),
            context_budget=self._budget(),
        )

        result = await orchestrator.execute(work)

        trace_present = [
            step_result.context_trace is not None for step_result in result.step_results
        ]
        traced_contexts = [
            (
                [
                    provider_trace.context.model_dump(mode="json")
                    for provider_trace in step_result.context_trace.provider_traces
                ]
                if step_result.context_trace is not None
                else []
            )
            for step_result in result.step_results
        ]

        bindings_cleared = all(
            bindings.resolve(run_id) is None and not bindings.is_required(run_id)
            for run_id in runtime.run_ids
        )

        return {
            "work_status": result.status.value,
            "executed_step_ids": [step_result.step_id for step_result in result.step_results],
            "run_statuses": [step_result.run.status.value for step_result in result.step_results],
            "work_contexts": [context.model_dump(mode="json") for context in result.contexts],
            "trace_present": trace_present,
            "traced_contexts": traced_contexts,
            "bindings_cleared": bindings_cleared,
            "runtime_context_present": runtime.context_present,
            "runtime_required": runtime.required,
            "distinct_run_ids": (len(runtime.run_ids) == len(set(runtime.run_ids))),
        }

    async def _evaluate_missing_binding(
        self,
        case: EvaluationCase,
    ) -> dict[str, Any]:
        bindings = InMemoryRunContextBindings()
        run_id = self._run_id(case.case_id, "missing")
        bindings.require(run_id)

        status_code: int | None = None
        error_type: str | None = None

        try:
            inject_bound_context(
                self._base_request(run_id, "missing binding"),
                bindings,
                ReferenceMessageInjector(),
            )
        except HTTPException as exc:
            status_code = exc.status_code
            if isinstance(exc.detail, dict):
                detail_type = exc.detail.get("type")
                if isinstance(detail_type, str):
                    error_type = detail_type

        bindings.release(run_id)

        return {
            "gateway_status_code": status_code,
            "gateway_error_type": error_type,
            "bindings_cleared": (
                bindings.resolve(run_id) is None and not bindings.is_required(run_id)
            ),
        }

    async def _evaluate_multi_turn(
        self,
        case: EvaluationCase,
    ) -> dict[str, Any]:
        bindings = InMemoryRunContextBindings()
        run_id = self._run_id(case.case_id, "multi-turn")
        prepared = await self._prepare_special(
            namespace="project:homelab",
            objective="Use stable context.",
            step_input="Complete two model turns.",
        )
        bindings.require(run_id)
        bindings.bind(run_id, prepared)

        injector = ReferenceMessageInjector()
        system_message = "Platform system instruction."
        injected_requests = [
            inject_bound_context(
                self._base_request(
                    run_id,
                    user_content,
                    system_message=system_message,
                ),
                bindings,
                injector,
            )
            for user_content in (
                "first turn",
                "second turn",
            )
        ]

        counts = [len(self._context_messages(request, prepared)) for request in injected_requests]
        roles = [
            message.role
            for request in injected_requests
            for message in self._context_messages(request, prepared)
        ]
        context_role = roles[0].value if roles and all(role is roles[0] for role in roles) else None
        system_unchanged = all(
            [message.content for message in request.messages if message.role is MessageRole.SYSTEM]
            == [system_message]
            for request in injected_requests
        )
        binding_retained = bindings.resolve(run_id) == prepared and bindings.is_required(run_id)

        bindings.release(run_id)

        return {
            "context_message_counts": counts,
            "context_message_role": context_role,
            "system_messages_unchanged": system_unchanged,
            "binding_retained": binding_retained,
            "bindings_cleared": (
                bindings.resolve(run_id) is None and not bindings.is_required(run_id)
            ),
        }

    async def _evaluate_concurrent_isolation(
        self,
        case: EvaluationCase,
    ) -> dict[str, Any]:
        bindings = InMemoryRunContextBindings()
        run_a = self._run_id(case.case_id, "a")
        run_b = self._run_id(case.case_id, "b")
        prepared_a = await self._prepare_special(
            namespace="project:alpha",
            objective="Use alpha context.",
            step_input="Execute alpha.",
        )
        prepared_b = await self._prepare_special(
            namespace="project:beta",
            objective="Use beta context.",
            step_input="Execute beta.",
        )

        for run_id, prepared in (
            (run_a, prepared_a),
            (run_b, prepared_b),
        ):
            bindings.require(run_id)
            bindings.bind(run_id, prepared)

        injector = ReferenceMessageInjector()

        injected_a, injected_b = await asyncio.gather(
            asyncio.to_thread(
                inject_bound_context,
                self._base_request(run_a, "alpha"),
                bindings,
                injector,
            ),
            asyncio.to_thread(
                inject_bound_context,
                self._base_request(run_b, "beta"),
                bindings,
                injector,
            ),
        )

        messages_a = [message.content for message in injected_a.messages]
        messages_b = [message.content for message in injected_b.messages]

        isolated = (
            prepared_a.rendered.text in messages_a
            and prepared_b.rendered.text not in messages_a
            and prepared_b.rendered.text in messages_b
            and prepared_a.rendered.text not in messages_b
        )
        counts = [
            len(self._context_messages(injected_a, prepared_a)),
            len(self._context_messages(injected_b, prepared_b)),
        ]

        bindings.release(run_a)
        bindings.release(run_b)

        return {
            "isolated": isolated,
            "context_message_counts": counts,
            "bindings_cleared": all(
                bindings.resolve(run_id) is None and not bindings.is_required(run_id)
                for run_id in (run_a, run_b)
            ),
        }

    async def _evaluate_runtime_provider_independence(
        self,
        case: EvaluationCase,
        evaluation_input: ContextAwareExecutionEvaluationInput,
    ) -> dict[str, Any]:
        if evaluation_input.work is None:
            raise ValueError("work is required for the runtime/provider independence scenario.")

        runtime_a = await self._execute_work(
            evaluation_input.work,
            runtime_name="m11-eval-runtime-a",
        )
        runtime_b = await self._execute_work(
            evaluation_input.work,
            runtime_name="m11-eval-runtime-b",
        )

        bindings = InMemoryRunContextBindings()
        run_id = self._run_id(case.case_id, "provider")
        prepared = await self._prepare_special(
            namespace="project:portable",
            objective="Keep context provider neutral.",
            step_input="Generate a provider-neutral request.",
        )
        bindings.require(run_id)
        bindings.bind(run_id, prepared)

        injected = inject_bound_context(
            self._base_request(run_id, "provider-neutral"),
            bindings,
            ReferenceMessageInjector(),
        )

        model_a = _CapturingModel(
            provider="provider-a",
            model="model-a",
        )
        model_b = _CapturingModel(
            provider="provider-b",
            model="model-b",
        )
        gateway_a = ModelGateway(
            model=model_a,
            observer=_NoopObserver(),
        )
        gateway_b = ModelGateway(
            model=model_b,
            observer=_NoopObserver(),
        )

        await gateway_a.generate(injected)
        await gateway_b.generate(injected)

        provider_neutral = (
            len(model_a.requests) == 1
            and len(model_b.requests) == 1
            and model_a.requests[0] == model_b.requests[0]
            and model_a.requests[0] == injected
        )

        bindings.release(run_id)

        return {
            "equivalent_across_runtimes": runtime_a == runtime_b,
            "provider_neutral": provider_neutral,
            "bindings_cleared": (
                runtime_a["bindings_cleared"]
                and runtime_b["bindings_cleared"]
                and bindings.resolve(run_id) is None
                and not bindings.is_required(run_id)
            ),
        }

    def _build_prepare_context(self) -> PrepareContext:
        estimator = Utf8ByteTokenEstimator()
        return PrepareContext(
            planner=DeterministicRecallPlanner(),
            provider=_DeterministicContextProvider(),
            assembler=DeterministicContextAssembler(),
            budget_policy=DeterministicContextBudgetPolicy(
                estimator=estimator,
            ),
            token_estimator=estimator,
            renderer=MarkdownContextRenderer(),
            injector=ReferenceMessageInjector(),
            trace_builder=ContextTraceBuilder(),
        )

    async def _prepare_special(
        self,
        *,
        namespace: str,
        objective: str,
        step_input: str,
    ) -> ContextPreparationResult:
        return await self._build_prepare_context().execute(
            objective=objective,
            step_input=step_input,
            contexts=(
                ContextRef(
                    role=ContextRole.SUBJECT,
                    namespace=namespace,
                ),
            ),
            budget=self._budget(),
        )

    @staticmethod
    def _budget() -> ContextBudget:
        return ContextBudget(
            max_total_tokens=512,
            reserved_output_tokens=64,
        )

    @staticmethod
    def _run_id(
        case_id: str,
        suffix: str,
    ) -> UUID:
        return uuid5(
            NAMESPACE_URL,
            f"agent-platform:m11-eval:{case_id}:{suffix}",
        )

    @staticmethod
    def _base_request(
        run_id: UUID,
        user_content: str,
        *,
        system_message: str = "Platform system instruction.",
    ) -> ModelRequest:
        return ModelRequest(
            run_id=run_id,
            messages=[
                ModelMessage(
                    role=MessageRole.SYSTEM,
                    content=system_message,
                ),
                ModelMessage(
                    role=MessageRole.USER,
                    content=user_content,
                ),
            ],
        )

    @staticmethod
    def _context_messages(
        request: ModelRequest,
        prepared: ContextPreparationResult,
    ) -> list[ModelMessage]:
        return [
            message for message in request.messages if message.content == prepared.rendered.text
        ]
