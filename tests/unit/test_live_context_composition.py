from datetime import UTC, datetime
from uuid import UUID

import pytest

from agent_platform.adapters.memory.sqlite import SQLiteMemoryStore
from agent_platform.api.composition import build_context_preparation
from agent_platform.application.run_agent import RunAgent
from agent_platform.application.work_orchestrator import WorkOrchestrator
from agent_platform.domain.context import ContextRef, ContextRole
from agent_platform.domain.memory import MemoryRecord, MemoryScope
from agent_platform.domain.models import RuntimeRequest, RuntimeResult
from agent_platform.domain.observability import ObservationEvent
from agent_platform.domain.work import (
    WorkRequest,
    WorkStatus,
    WorkStep,
)


class RecordingRuntime:
    def __init__(self) -> None:
        self.calls: list[RuntimeRequest] = []

    @property
    def name(self) -> str:
        return "recording"

    async def execute(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResult:
        self.calls.append(request)
        return RuntimeResult(
            output=f"done:{request.input}",
        )


class NoopObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


def test_context_preparation_is_disabled_without_memory_db() -> None:
    assert build_context_preparation({}) is None


@pytest.mark.asyncio
async def test_context_preparation_uses_real_memory_pipeline(
    tmp_path,
) -> None:
    database_path = tmp_path / "memory.sqlite3"
    store = SQLiteMemoryStore(database_path)

    memory = MemoryRecord(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        scope=MemoryScope(
            namespace="project:homelab",
        ),
        content="homelab monitoring draft",
        created_at=datetime(
            2026,
            9,
            17,
            12,
            0,
            tzinfo=UTC,
        ),
        metadata={"kind": "project-reference"},
    )
    await store.store(memory)

    composition = build_context_preparation(
        {
            "AGENT_PLATFORM_MEMORY_DB": str(database_path),
            "AGENT_PLATFORM_CONTEXT_MAX_TOTAL_TOKENS": "512",
            "AGENT_PLATFORM_CONTEXT_BASE_INPUT_TOKENS": "0",
            "AGENT_PLATFORM_CONTEXT_RESERVED_OUTPUT_TOKENS": "64",
        }
    )

    assert composition is not None
    prepare_context, budget = composition

    result = await prepare_context.execute(
        objective="homelab monitoring",
        step_input="draft",
        contexts=[
            ContextRef(
                role=ContextRole.SUBJECT,
                namespace="project:homelab",
            )
        ],
        budget=budget,
    )

    assert result.rendered.text
    assert len(result.trace.provider_traces) == 1
    provider_trace = result.trace.provider_traces[0]
    assert provider_trace.context.namespace == "project:homelab"
    assert provider_trace.decision.value == "accept"
    assert provider_trace.accepted_count == 1
    assert provider_trace.accepted_sources[0].source_id == str(memory.id)


def test_context_preparation_rejects_invalid_budget() -> None:
    with pytest.raises(
        ValueError,
        match="AGENT_PLATFORM_CONTEXT_MAX_TOTAL_TOKENS",
    ):
        build_context_preparation(
            {
                "AGENT_PLATFORM_MEMORY_DB": "memory.sqlite3",
                "AGENT_PLATFORM_CONTEXT_MAX_TOTAL_TOKENS": "invalid",
            }
        )


@pytest.mark.asyncio
async def test_context_work_without_preparer_fails_closed() -> None:
    runtime = RecordingRuntime()
    orchestrator = WorkOrchestrator(
        RunAgent(
            runtime=runtime,
            observer=NoopObserver(),
        )
    )

    result = await orchestrator.execute(
        WorkRequest(
            objective="homelab monitoring",
            contexts=[
                ContextRef(
                    role=ContextRole.SUBJECT,
                    namespace="project:homelab",
                )
            ],
            steps=[
                WorkStep(
                    step_id="draft",
                    agent_id="writer",
                    input="draft",
                )
            ],
        )
    )

    assert result.status is WorkStatus.FAILED
    assert result.failed_step_id == "draft"
    assert runtime.calls == []
    assert result.step_results[0].run.error == "context preparation is not configured."


@pytest.mark.asyncio
async def test_context_free_work_without_preparer_remains_valid() -> None:
    runtime = RecordingRuntime()
    orchestrator = WorkOrchestrator(
        RunAgent(
            runtime=runtime,
            observer=NoopObserver(),
        )
    )

    result = await orchestrator.execute(
        WorkRequest(
            objective="plain execution",
            steps=[
                WorkStep(
                    step_id="run",
                    agent_id="worker",
                    input="execute",
                )
            ],
        )
    )

    assert result.status is WorkStatus.SUCCEEDED
    assert len(runtime.calls) == 1
