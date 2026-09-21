from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from agent_platform.adapters.capabilities.coding import (
    SupervisedCodingCapability,
)
from agent_platform.adapters.tools.coding import CodingTool
from agent_platform.application.capability_authorization import (
    StaticCapabilityAuthorizationPolicy,
)
from agent_platform.application.supervised_coding import PreparedCodingTask
from agent_platform.application.supervised_coding_publication import (
    SupervisedCodingPublicationService,
)
from agent_platform.application.tool_registry import ToolRegistry
from agent_platform.domain.observability import ObservationEvent
from agent_platform.domain.tool import ToolRequest
from agent_platform.trust.change_set_identity import identify_change_set
from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
)
from agent_platform.trust.verification import (
    VerificationOutcome,
    VerificationResult,
    VerificationStepResult,
)
from agent_platform.trust.verification_binding import VerifiedChangeSet
from agent_platform.trust.verification_profile import VerificationCheck
from agent_platform.trust.verified_publication import VerifiedPublicationResult

RUN_ID = UUID("13000000-0000-4000-8000-000000000020")
EXECUTION_ID = UUID("13000000-0000-4000-8000-000000000021")
BASE_REVISION = "a" * 40


class NullObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


def _change_set() -> ChangeSet:
    return ChangeSet(
        base_revision=BASE_REVISION,
        branch_name="coding/capability-trace",
        commit_message="test: capability trace correlation",
        changes=(
            FileChange(
                path="src/example.py",
                operation=FileChangeOperation.UPSERT,
                content="VALUE = 1\n",
            ),
        ),
    )


def _verified(
    change_set: ChangeSet,
) -> VerifiedChangeSet:
    return VerifiedChangeSet(
        change_set=change_set,
        identity=identify_change_set(change_set),
        verification=VerificationResult(
            profile_version="m12-v0",
            outcome=VerificationOutcome.PASS,
            reason_code="all_checks_passed",
            steps=(
                VerificationStepResult(
                    check=VerificationCheck.SYNTAX,
                    outcome=VerificationOutcome.PASS,
                    exit_code=0,
                    summary="pass",
                ),
            ),
        ),
    )


@dataclass
class DynamicPreparation:
    change_set: ChangeSet

    async def execute(
        self,
        task,
    ) -> PreparedCodingTask:
        return PreparedCodingTask(
            task_id=task.task_id,
            execution_id=EXECUTION_ID,
            change_set=self.change_set,
        )


@dataclass
class StaticVerification:
    verified: VerifiedChangeSet

    async def verify(
        self,
        change_set: ChangeSet,
    ) -> VerifiedChangeSet:
        assert change_set == self.verified.change_set
        return self.verified


@dataclass
class StaticPublisher:
    verified: VerifiedChangeSet

    async def publish(
        self,
        verified: VerifiedChangeSet,
    ) -> VerifiedPublicationResult:
        assert verified == self.verified

        return VerifiedPublicationResult(
            reference=("https://github.com/kersbaumerHugo/agent-platform/pull/123"),
            identity=verified.identity,
        )


@pytest.mark.asyncio
async def test_tool_to_capability_preserves_coding_trace_context() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    tracer = provider.get_tracer("agent-platform-capability-correlation-test")

    change_set = _change_set()
    verified = _verified(change_set)

    coding_service = SupervisedCodingPublicationService(
        preparation=DynamicPreparation(change_set),
        verification=StaticVerification(verified),
        publisher=StaticPublisher(verified),
        tracer=tracer,
    )

    capability = SupervisedCodingCapability(coding_service)

    tool = CodingTool(
        capability,
        StaticCapabilityAuthorizationPolicy(
            grants=[
                (
                    "agent:trace-test",
                    "coding.execute",
                )
            ]
        ),
    )

    registry = ToolRegistry(
        [tool],
        NullObserver(),
        tracer=tracer,
    )

    result = await registry.invoke(
        "coding_execute",
        ToolRequest(
            run_id=RUN_ID,
            principal_id="agent:trace-test",
            arguments={
                "goal": "Change one controlled file.",
                "expected_base_revision": BASE_REVISION,
            },
        ),
    )

    spans = exporter.get_finished_spans()

    assert len(spans) == 2

    tool_span = next(span for span in spans if span.name == "tool.invoke")
    coding_span = next(span for span in spans if span.name == "coding.supervised")

    assert tool_span.context is not None
    assert coding_span.parent is not None
    assert coding_span.parent.span_id == tool_span.context.span_id

    assert tool_span.attributes is not None
    assert coding_span.attributes is not None

    assert tool_span.attributes["agent_platform.run.id"] == str(RUN_ID)
    assert tool_span.attributes["agent_platform.tool.name"] == "coding_execute"

    assert coding_span.attributes["agent_platform.coding.task.id"] == result.output["task_id"]
    assert (
        coding_span.attributes["agent_platform.coding.execution.id"]
        == result.output["execution_id"]
    )
    assert (
        coding_span.attributes["agent_platform.coding.change_set.identity"]
        == result.output["change_set_identity"]
    )
    assert coding_span.attributes["agent_platform.coding.verification.outcome"] == "pass"
    assert coding_span.attributes["agent_platform.coding.publication.outcome"] == "published"
