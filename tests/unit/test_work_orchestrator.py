import pytest

from agent_platform.application.run_agent import RunAgent
from agent_platform.application.work_orchestrator import WorkOrchestrator
from agent_platform.domain.models import (
    RunStatus,
    RuntimeRequest,
    RuntimeResult,
)
from agent_platform.domain.observability import ObservationEvent
from agent_platform.domain.work import (
    ContextRef,
    ContextRole,
    WorkRequest,
    WorkStatus,
    WorkStep,
)


class RecordingRuntime:
    def __init__(self, fail_on_input: str | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_on_input = fail_on_input

    @property
    def name(self) -> str:
        return "recording"

    async def execute(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResult:
        self.calls.append(
            (
                request.agent_id,
                request.input,
            )
        )

        if request.input == self.fail_on_input:
            raise RuntimeError("planned runtime failure")

        return RuntimeResult(
            output=f"{request.agent_id}:{request.input}",
        )


class NoopObserver:
    def record(self, event: ObservationEvent) -> None:
        del event


def make_orchestrator(
    runtime: RecordingRuntime,
) -> WorkOrchestrator:
    return WorkOrchestrator(
        RunAgent(
            runtime=runtime,
            observer=NoopObserver(),
        )
    )


@pytest.mark.asyncio
async def test_single_step_work_succeeds() -> None:
    runtime = RecordingRuntime()
    orchestrator = make_orchestrator(runtime)

    result = await orchestrator.execute(
        WorkRequest(
            objective="Draft a post.",
            steps=[
                WorkStep(
                    step_id="draft",
                    agent_id="writer",
                    input="draft",
                )
            ],
        )
    )

    assert result.status is WorkStatus.SUCCEEDED
    assert result.failed_step_id is None
    assert len(result.step_results) == 1
    assert result.step_results[0].step_id == "draft"
    assert result.step_results[0].run.status is RunStatus.SUCCEEDED
    assert runtime.calls == [
        ("writer", "draft"),
    ]
    assert result.finished_at is not None


@pytest.mark.asyncio
async def test_multi_step_work_preserves_declared_order() -> None:
    runtime = RecordingRuntime()
    orchestrator = make_orchestrator(runtime)

    result = await orchestrator.execute(
        WorkRequest(
            objective="Draft and review.",
            steps=[
                WorkStep(
                    step_id="draft",
                    agent_id="writer",
                    input="first",
                ),
                WorkStep(
                    step_id="review",
                    agent_id="reviewer",
                    input="second",
                ),
                WorkStep(
                    step_id="finalize",
                    agent_id="writer",
                    input="third",
                ),
            ],
        )
    )

    assert result.status is WorkStatus.SUCCEEDED
    assert runtime.calls == [
        ("writer", "first"),
        ("reviewer", "second"),
        ("writer", "third"),
    ]
    assert [step_result.step_id for step_result in result.step_results] == [
        "draft",
        "review",
        "finalize",
    ]


@pytest.mark.asyncio
async def test_failure_stops_later_steps_and_preserves_results() -> None:
    runtime = RecordingRuntime(
        fail_on_input="fail",
    )
    orchestrator = make_orchestrator(runtime)

    result = await orchestrator.execute(
        WorkRequest(
            objective="Stop after failure.",
            steps=[
                WorkStep(
                    step_id="first",
                    agent_id="worker",
                    input="ok",
                ),
                WorkStep(
                    step_id="second",
                    agent_id="worker",
                    input="fail",
                ),
                WorkStep(
                    step_id="third",
                    agent_id="worker",
                    input="must-not-run",
                ),
            ],
        )
    )

    assert result.status is WorkStatus.FAILED
    assert result.failed_step_id == "second"
    assert runtime.calls == [
        ("worker", "ok"),
        ("worker", "fail"),
    ]
    assert [step_result.step_id for step_result in result.step_results] == [
        "first",
        "second",
    ]
    assert result.step_results[0].run.status is RunStatus.SUCCEEDED
    assert result.step_results[1].run.status is RunStatus.FAILED
    assert result.finished_at is not None


@pytest.mark.asyncio
async def test_explicit_contexts_are_preserved_without_additions() -> None:
    runtime = RecordingRuntime()
    orchestrator = make_orchestrator(runtime)
    contexts = [
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
    ]

    result = await orchestrator.execute(
        WorkRequest(
            objective="Write about the homelab on LinkedIn.",
            contexts=contexts,
            steps=[
                WorkStep(
                    step_id="draft",
                    agent_id="writer",
                    input="draft",
                )
            ],
        )
    )

    assert result.contexts == contexts
    assert {(context.role, context.namespace) for context in result.contexts} == {
        (ContextRole.SHARED, "global"),
        (ContextRole.DELIVERY, "app:linkedin"),
        (ContextRole.SUBJECT, "project:homelab"),
    }
    assert all(context.namespace != "project:agent-platform" for context in result.contexts)
