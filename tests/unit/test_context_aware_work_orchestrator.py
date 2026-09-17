from uuid import UUID

import pytest

from agent_platform.application.run_agent import RunAgent
from agent_platform.application.run_context import InMemoryRunContextBindings
from agent_platform.application.work_orchestrator import WorkOrchestrator
from agent_platform.domain.context import (
    ContextRef,
    ContextRole,
    content_sha256,
)
from agent_platform.domain.context_budget import ContextBudget
from agent_platform.domain.context_preparation import (
    ContextPreparationResult,
)
from agent_platform.domain.context_rendering import RenderedContext
from agent_platform.domain.context_trace import (
    ContextBudgetTrace,
    ContextInjectionTrace,
    ContextPreparationTrace,
    ContextRenderingTrace,
)
from agent_platform.domain.models import (
    RunRequest,
    RunStatus,
    RuntimeRequest,
    RuntimeResult,
)
from agent_platform.domain.observability import ObservationEvent
from agent_platform.domain.work import (
    WorkRequest,
    WorkStatus,
    WorkStep,
)


class RecordingPreparer:
    def __init__(
        self,
        *,
        fail_on_step_input: str | None = None,
    ) -> None:
        self.calls: list[tuple[str, str, tuple[ContextRef, ...], ContextBudget]] = []
        self.fail_on_step_input = fail_on_step_input

    async def execute(
        self,
        *,
        objective: str,
        step_input: str,
        contexts: list[ContextRef],
        budget: ContextBudget,
    ) -> ContextPreparationResult:
        self.calls.append(
            (
                objective,
                step_input,
                tuple(contexts),
                budget,
            )
        )

        if step_input == self.fail_on_step_input:
            raise RuntimeError("planned preparation failure")

        return make_prepared_context(f"prepared:{objective}:{step_input}")


class BindingAwareRuntime:
    def __init__(
        self,
        bindings: InMemoryRunContextBindings,
        *,
        fail_on_input: str | None = None,
    ) -> None:
        self._bindings = bindings
        self._fail_on_input = fail_on_input
        self.calls: list[tuple[UUID, str, str, ContextPreparationResult | None, bool]] = []

    @property
    def name(self) -> str:
        return "binding-aware"

    async def execute(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResult:
        prepared = self._bindings.resolve(request.run_id)
        required = self._bindings.is_required(request.run_id)

        self.calls.append(
            (
                request.run_id,
                request.agent_id,
                request.input,
                prepared,
                required,
            )
        )

        if request.input == self._fail_on_input:
            raise RuntimeError("planned runtime failure")

        return RuntimeResult(
            output=f"{request.agent_id}:{request.input}",
        )


class NoopObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


def make_prepared_context(
    text: str,
) -> ContextPreparationResult:
    content_hash = content_sha256(text)
    rendered = RenderedContext(
        renderer="markdown",
        version="v0",
        text=text,
        content_hash=content_hash,
    )

    return ContextPreparationResult(
        rendered=rendered,
        trace=ContextPreparationTrace(
            version="v0",
            planner="deterministic",
            planner_version="v0",
            provider_traces=(),
            assembler_version="v0",
            budget=ContextBudgetTrace(
                policy_version="canonical-prefix-v0",
                estimator_version="utf8-bytes-v0",
                budget_tokens=128,
                estimated_tokens=1 if text else 0,
                dropped_item_ids=(),
            ),
            rendering=ContextRenderingTrace(
                renderer=rendered.renderer,
                version=rendered.version,
                content_hash=rendered.content_hash,
            ),
            injection=ContextInjectionTrace(
                injector="reference-message",
                version="v0",
            ),
        ),
    )


def make_context() -> ContextRef:
    return ContextRef(
        role=ContextRole.SUBJECT,
        namespace="project:homelab",
    )


def make_orchestrator(
    *,
    runtime: BindingAwareRuntime,
    bindings: InMemoryRunContextBindings,
    preparer: RecordingPreparer | None,
) -> WorkOrchestrator:
    run_agent = RunAgent(
        runtime=runtime,
        observer=NoopObserver(),
        run_context_bindings=bindings,
    )

    if preparer is None:
        return WorkOrchestrator(run_agent)

    return WorkOrchestrator(
        run_agent,
        prepare_context=preparer,
        context_budget=ContextBudget(
            max_total_tokens=256,
            reserved_output_tokens=32,
        ),
    )


@pytest.mark.asyncio
async def test_context_aware_step_binds_during_runtime_and_releases_after() -> None:
    bindings = InMemoryRunContextBindings()
    preparer = RecordingPreparer()
    runtime = BindingAwareRuntime(bindings)
    orchestrator = make_orchestrator(
        runtime=runtime,
        bindings=bindings,
        preparer=preparer,
    )

    result = await orchestrator.execute(
        WorkRequest(
            objective="Write about the homelab.",
            contexts=[make_context()],
            steps=[
                WorkStep(
                    step_id="draft",
                    agent_id="writer",
                    input="Draft the post.",
                )
            ],
        )
    )

    assert result.status is WorkStatus.SUCCEEDED
    assert len(preparer.calls) == 1
    assert len(runtime.calls) == 1

    run_id, _, _, prepared, required = runtime.calls[0]

    assert prepared is not None
    assert required is True
    assert prepared.rendered.text == ("prepared:Write about the homelab.:Draft the post.")
    assert bindings.resolve(run_id) is None
    assert bindings.is_required(run_id) is False


@pytest.mark.asyncio
async def test_two_steps_prepare_independently_and_use_distinct_run_ids() -> None:
    bindings = InMemoryRunContextBindings()
    preparer = RecordingPreparer()
    runtime = BindingAwareRuntime(bindings)
    orchestrator = make_orchestrator(
        runtime=runtime,
        bindings=bindings,
        preparer=preparer,
    )
    context = make_context()

    result = await orchestrator.execute(
        WorkRequest(
            objective="Publish a homelab update.",
            contexts=[context],
            steps=[
                WorkStep(
                    step_id="draft",
                    agent_id="writer",
                    input="Draft the opening.",
                ),
                WorkStep(
                    step_id="finish",
                    agent_id="writer",
                    input="Draft the conclusion.",
                ),
            ],
        )
    )

    assert result.status is WorkStatus.SUCCEEDED
    assert [call[1] for call in preparer.calls] == [
        "Draft the opening.",
        "Draft the conclusion.",
    ]
    assert all(call[2] == (context,) for call in preparer.calls)

    run_ids = [call[0] for call in runtime.calls]
    assert run_ids[0] != run_ids[1]
    assert all(call[3] is not None for call in runtime.calls)
    assert all(call[4] is True for call in runtime.calls)
    assert all(bindings.resolve(run_id) is None for run_id in run_ids)


@pytest.mark.asyncio
async def test_no_context_work_remains_backward_compatible() -> None:
    bindings = InMemoryRunContextBindings()
    preparer = RecordingPreparer()
    runtime = BindingAwareRuntime(bindings)
    orchestrator = make_orchestrator(
        runtime=runtime,
        bindings=bindings,
        preparer=preparer,
    )

    result = await orchestrator.execute(
        WorkRequest(
            objective="Run without context.",
            steps=[
                WorkStep(
                    step_id="execute",
                    agent_id="worker",
                    input="Execute.",
                )
            ],
        )
    )

    assert result.status is WorkStatus.SUCCEEDED
    assert preparer.calls == []
    assert len(runtime.calls) == 1
    assert runtime.calls[0][3] is None
    assert runtime.calls[0][4] is False


@pytest.mark.asyncio
async def test_preparation_failure_prevents_runtime_execution() -> None:
    bindings = InMemoryRunContextBindings()
    preparer = RecordingPreparer(
        fail_on_step_input="fail preparation",
    )
    runtime = BindingAwareRuntime(bindings)
    orchestrator = make_orchestrator(
        runtime=runtime,
        bindings=bindings,
        preparer=preparer,
    )

    result = await orchestrator.execute(
        WorkRequest(
            objective="Prepare then execute.",
            contexts=[make_context()],
            steps=[
                WorkStep(
                    step_id="prepare",
                    agent_id="worker",
                    input="fail preparation",
                )
            ],
        )
    )

    assert result.status is WorkStatus.FAILED
    assert result.failed_step_id == "prepare"
    assert runtime.calls == []
    assert len(result.step_results) == 1

    run = result.step_results[0].run
    assert run.status is RunStatus.FAILED
    assert run.error is not None
    assert "context preparation failed" in run.error


@pytest.mark.asyncio
async def test_runtime_failure_releases_context_binding() -> None:
    bindings = InMemoryRunContextBindings()
    preparer = RecordingPreparer()
    runtime = BindingAwareRuntime(
        bindings,
        fail_on_input="fail runtime",
    )
    orchestrator = make_orchestrator(
        runtime=runtime,
        bindings=bindings,
        preparer=preparer,
    )

    result = await orchestrator.execute(
        WorkRequest(
            objective="Execute with context.",
            contexts=[make_context()],
            steps=[
                WorkStep(
                    step_id="execute",
                    agent_id="worker",
                    input="fail runtime",
                )
            ],
        )
    )

    assert result.status is WorkStatus.FAILED
    assert len(runtime.calls) == 1

    run_id = runtime.calls[0][0]
    assert runtime.calls[0][3] is not None
    assert runtime.calls[0][4] is True
    assert bindings.resolve(run_id) is None
    assert bindings.is_required(run_id) is False


@pytest.mark.asyncio
async def test_prepared_context_without_bindings_fails_before_runtime() -> None:
    bindings = InMemoryRunContextBindings()
    runtime = BindingAwareRuntime(bindings)
    run_agent = RunAgent(
        runtime=runtime,
        observer=NoopObserver(),
    )

    run = await run_agent.execute(
        RunRequest(
            agent_id="worker",
            input="execute",
        ),
        prepared_context=make_prepared_context("context"),
    )

    assert run.status is RunStatus.FAILED
    assert run.error == ("Prepared context requires run-scoped context bindings.")
    assert runtime.calls == []
