from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from agent_platform.adapters.tools.coding import CodingTool
from agent_platform.application.capability_authorization import (
    StaticCapabilityAuthorizationPolicy,
)
from agent_platform.application.tool_registry import ToolRegistry
from agent_platform.domain.capability import CapabilityDefinition
from agent_platform.domain.coding import (
    CodingPublicationOutcome,
    CodingResult,
    CodingTask,
    CodingVerificationOutcome,
)
from agent_platform.domain.observability import ObservationEvent
from agent_platform.domain.tool import ToolRequest

RUN_ID = UUID("13000000-0000-4000-8000-000000000030")
TASK_ID = UUID("13000000-0000-4000-8000-000000000031")
EXECUTION_ID = UUID("13000000-0000-4000-8000-000000000032")

BASE_REVISION = "a" * 40
CHANGE_SET_IDENTITY = f"v1:sha256:{'b' * 64}"


class NullObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


@dataclass
class RecordingCapability:
    requests: list[CodingTask] = field(default_factory=list)

    @property
    def definition(self) -> CapabilityDefinition:
        return CapabilityDefinition(
            name="coding.execute",
            description="Execute supervised coding.",
        )

    async def invoke(
        self,
        request: CodingTask,
    ) -> CodingResult:
        self.requests.append(request)

        return CodingResult(
            task_id=TASK_ID,
            execution_id=EXECUTION_ID,
            base_revision=BASE_REVISION,
            change_set_identity=CHANGE_SET_IDENTITY,
            changed_paths=("src/example.py",),
            verification_profile_version="m12-v0",
            verification_outcome=CodingVerificationOutcome.PASS,
            publication_outcome=CodingPublicationOutcome.PUBLISHED,
            publication_reference=("https://github.com/kersbaumerHugo/agent-platform/pull/123"),
            pull_request_number=123,
        )


@pytest.mark.asyncio
async def test_registry_allows_granted_principal() -> None:
    capability = RecordingCapability()

    tool = CodingTool(
        capability,
        StaticCapabilityAuthorizationPolicy(
            grants=[
                (
                    "agent:developer",
                    "coding.execute",
                )
            ]
        ),
    )

    registry = ToolRegistry(
        [tool],
        NullObserver(),
    )

    result = await registry.invoke(
        "coding_execute",
        ToolRequest(
            run_id=RUN_ID,
            principal_id="agent:developer",
            arguments={
                "goal": "Change one controlled file.",
                "expected_base_revision": BASE_REVISION,
            },
        ),
    )

    assert len(capability.requests) == 1
    assert result.run_id == RUN_ID
    assert result.tool_name == "coding_execute"


@pytest.mark.asyncio
async def test_registry_denies_anonymous_principal_before_capability() -> None:
    capability = RecordingCapability()

    tool = CodingTool(
        capability,
        StaticCapabilityAuthorizationPolicy(),
    )

    registry = ToolRegistry(
        [tool],
        NullObserver(),
    )

    with pytest.raises(
        PermissionError,
        match="capability_not_granted",
    ):
        await registry.invoke(
            "coding_execute",
            ToolRequest(
                run_id=RUN_ID,
                principal_id="mcp:anonymous",
                arguments={
                    "goal": "Change one controlled file.",
                    "expected_base_revision": BASE_REVISION,
                },
            ),
        )

    assert capability.requests == []


@pytest.mark.asyncio
async def test_denied_invocation_emits_only_tool_span() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()

    provider.add_span_processor(SimpleSpanProcessor(exporter))

    tracer = provider.get_tracer("agent-platform-authorization-boundary-test")

    capability = RecordingCapability()

    tool = CodingTool(
        capability,
        StaticCapabilityAuthorizationPolicy(),
    )

    registry = ToolRegistry(
        [tool],
        NullObserver(),
        tracer=tracer,
    )

    with pytest.raises(PermissionError):
        await registry.invoke(
            "coding_execute",
            ToolRequest(
                run_id=RUN_ID,
                principal_id="mcp:anonymous",
                arguments={
                    "goal": "Change one controlled file.",
                    "expected_base_revision": BASE_REVISION,
                },
            ),
        )

    spans = exporter.get_finished_spans()

    assert len(spans) == 1
    assert spans[0].name == "tool.invoke"

    assert capability.requests == []
