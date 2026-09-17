import json
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
        raw_prefix: str = "raw-reference",
        fail_on_step_input: str | None = None,
    ) -> None:
        self._raw_prefix = raw_prefix
        self._fail_on_step_input = fail_on_step_input
        self.results: list[ContextPreparationResult] = []

    async def execute(
        self,
        *,
        objective: str,
        step_input: str,
        contexts: list[ContextRef],
        budget: ContextBudget,
    ) -> ContextPreparationResult:
        del objective, contexts, budget

        if step_input == self._fail_on_step_input:
            raise RuntimeError("planned preparation failure")

        result = make_prepared_context(f"{self._raw_prefix}:{step_input}")
        self.results.append(result)
        return result


class RecordingRuntime:
    def __init__(self) -> None:
        self.run_ids: list[UUID] = []

    @property
    def name(self) -> str:
        return "recording"

    async def execute(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResult:
        self.run_ids.append(request.run_id)
        return RuntimeResult(
            output=f"done:{request.input}",
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
                estimated_tokens=1,
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
    preparer: RecordingPreparer,
    runtime: RecordingRuntime,
    bindings: InMemoryRunContextBindings,
) -> WorkOrchestrator:
    return WorkOrchestrator(
        RunAgent(
            runtime=runtime,
            observer=NoopObserver(),
            run_context_bindings=bindings,
        ),
        prepare_context=preparer,
        context_budget=ContextBudget(
            max_total_tokens=256,
            reserved_output_tokens=32,
        ),
    )


@pytest.mark.asyncio
async def test_step_result_correlates_work_step_run_and_context_trace() -> None:
    bindings = InMemoryRunContextBindings()
    preparer = RecordingPreparer()
    runtime = RecordingRuntime()
    orchestrator = make_orchestrator(
        preparer=preparer,
        runtime=runtime,
        bindings=bindings,
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
    assert len(result.step_results) == 1
    assert len(preparer.results) == 1
    assert len(runtime.run_ids) == 1

    step_result = result.step_results[0]
    prepared = preparer.results[0]
    run_id = runtime.run_ids[0]

    assert result.work_id is not None
    assert step_result.step_id == "draft"
    assert step_result.run.run_id == run_id
    assert step_result.context_trace == prepared.trace
    assert step_result.context_trace is not None
    assert step_result.context_trace.rendering.content_hash == prepared.rendered.content_hash
    assert bindings.resolve(run_id) is None
    assert bindings.is_required(run_id) is False


@pytest.mark.asyncio
async def test_two_steps_keep_distinct_run_and_context_correlations() -> None:
    bindings = InMemoryRunContextBindings()
    preparer = RecordingPreparer()
    runtime = RecordingRuntime()
    orchestrator = make_orchestrator(
        preparer=preparer,
        runtime=runtime,
        bindings=bindings,
    )

    result = await orchestrator.execute(
        WorkRequest(
            objective="Publish a homelab update.",
            contexts=[make_context()],
            steps=[
                WorkStep(
                    step_id="draft",
                    agent_id="writer",
                    input="Draft opening.",
                ),
                WorkStep(
                    step_id="finish",
                    agent_id="writer",
                    input="Draft conclusion.",
                ),
            ],
        )
    )

    assert result.status is WorkStatus.SUCCEEDED
    assert len(result.step_results) == 2

    first, second = result.step_results

    assert first.run.run_id != second.run.run_id
    assert first.context_trace is not None
    assert second.context_trace is not None
    assert first.context_trace.rendering.content_hash != second.context_trace.rendering.content_hash
    assert first.context_trace == preparer.results[0].trace
    assert second.context_trace == preparer.results[1].trace


@pytest.mark.asyncio
async def test_context_free_work_has_no_context_trace() -> None:
    bindings = InMemoryRunContextBindings()
    preparer = RecordingPreparer()
    runtime = RecordingRuntime()
    orchestrator = make_orchestrator(
        preparer=preparer,
        runtime=runtime,
        bindings=bindings,
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
    assert preparer.results == []
    assert result.step_results[0].context_trace is None


@pytest.mark.asyncio
async def test_preparation_failure_has_no_context_trace() -> None:
    bindings = InMemoryRunContextBindings()
    preparer = RecordingPreparer(
        fail_on_step_input="fail preparation",
    )
    runtime = RecordingRuntime()
    orchestrator = make_orchestrator(
        preparer=preparer,
        runtime=runtime,
        bindings=bindings,
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
    assert runtime.run_ids == []
    assert result.step_results[0].context_trace is None


@pytest.mark.asyncio
async def test_work_trace_serialization_excludes_raw_prepared_context() -> None:
    marker = "RAW-CONTEXT-MUST-NOT-LEAK"
    bindings = InMemoryRunContextBindings()
    preparer = RecordingPreparer(
        raw_prefix=marker,
    )
    runtime = RecordingRuntime()
    orchestrator = make_orchestrator(
        preparer=preparer,
        runtime=runtime,
        bindings=bindings,
    )

    result = await orchestrator.execute(
        WorkRequest(
            objective="Use private reference material.",
            contexts=[make_context()],
            steps=[
                WorkStep(
                    step_id="draft",
                    agent_id="writer",
                    input="Draft safely.",
                )
            ],
        )
    )

    serialized = json.dumps(
        result.model_dump(mode="json"),
        sort_keys=True,
    )

    assert marker not in serialized
    assert result.step_results[0].context_trace is not None
    assert (
        result.step_results[0].context_trace.rendering.content_hash
        == preparer.results[0].rendered.content_hash
    )
