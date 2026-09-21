from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode

from agent_platform.application.supervised_coding import PreparedCodingTask
from agent_platform.application.supervised_coding_publication import (
    CodingPublicationIdentityMismatchError,
    SupervisedCodingPublicationService,
)
from agent_platform.domain.coding import CodingTask
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

TASK_ID = UUID("12000000-0000-4000-8000-00000000000b")
EXECUTION_ID = UUID("12000000-0000-4000-8000-00000000000c")
BASE_REVISION = "a" * 40
SECRET_GOAL = "raw coding goal must not enter telemetry"


def _task() -> CodingTask:
    return CodingTask(
        task_id=TASK_ID,
        goal=SECRET_GOAL,
        expected_base_revision=BASE_REVISION,
    )


def _change_set() -> ChangeSet:
    return ChangeSet(
        base_revision=BASE_REVISION,
        branch_name=f"coding/{TASK_ID}",
        commit_message=f"chore: apply supervised coding task {TASK_ID}",
        changes=(
            FileChange(
                path="src/example.py",
                operation=FileChangeOperation.UPSERT,
                content="SENSITIVE_CONTENT = 1\n",
            ),
        ),
    )


def _verified(change_set: ChangeSet) -> VerifiedChangeSet:
    verification = VerificationResult(
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
    )

    return VerifiedChangeSet(
        change_set=change_set,
        identity=identify_change_set(change_set),
        verification=verification,
    )


@dataclass
class StaticPreparation:
    prepared: PreparedCodingTask

    async def execute(
        self,
        task: CodingTask,
    ) -> PreparedCodingTask:
        del task
        return self.prepared


@dataclass
class StaticVerification:
    verified: VerifiedChangeSet

    async def verify(
        self,
        change_set: ChangeSet,
    ) -> VerifiedChangeSet:
        del change_set
        return self.verified


@dataclass
class StaticPublisher:
    result: VerifiedPublicationResult

    async def publish(
        self,
        verified: VerifiedChangeSet,
    ) -> VerifiedPublicationResult:
        del verified
        return self.result


def _tracer():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    return exporter, provider.get_tracer("agent-platform-coding-test")


@pytest.mark.asyncio
async def test_supervised_coding_emits_safe_correlation_span() -> None:
    change_set = _change_set()
    verified = _verified(change_set)
    exporter, tracer = _tracer()

    service = SupervisedCodingPublicationService(
        preparation=StaticPreparation(
            PreparedCodingTask(
                task_id=TASK_ID,
                execution_id=EXECUTION_ID,
                change_set=change_set,
            )
        ),
        verification=StaticVerification(verified),
        publisher=StaticPublisher(
            VerifiedPublicationResult(
                reference="https://github.com/kersbaumerHugo/agent-platform/pull/123",
                identity=verified.identity,
            )
        ),
        tracer=tracer,
    )

    result = await service.execute(_task())

    spans = exporter.get_finished_spans()

    assert len(spans) == 1

    span = spans[0]

    assert span.name == "coding.supervised"
    assert span.status.status_code is StatusCode.OK
    assert span.attributes is not None

    assert span.attributes["agent_platform.coding.task.id"] == str(TASK_ID)
    assert span.attributes["agent_platform.coding.execution.id"] == str(result.execution_id)
    assert span.attributes["agent_platform.coding.base_revision"] == BASE_REVISION
    assert (
        span.attributes["agent_platform.coding.change_set.identity"] == result.change_set_identity
    )
    assert (
        span.attributes["agent_platform.coding.verification.profile"]
        == result.verification_profile_version
    )
    assert span.attributes["agent_platform.coding.verification.outcome"] == "pass"
    assert span.attributes["agent_platform.coding.publication.outcome"] == "published"

    serialized_attributes = repr(dict(span.attributes))

    assert SECRET_GOAL not in serialized_attributes
    assert "SENSITIVE_CONTENT" not in serialized_attributes
    assert "stdout" not in serialized_attributes
    assert "stderr" not in serialized_attributes
    assert "environment" not in serialized_attributes


@pytest.mark.asyncio
async def test_supervised_coding_trace_marks_fail_closed_error() -> None:
    change_set = _change_set()
    verified = _verified(change_set)

    different_change_set = ChangeSet(
        base_revision=change_set.base_revision,
        branch_name="coding/different",
        commit_message=change_set.commit_message,
        changes=change_set.changes,
    )

    exporter, tracer = _tracer()

    service = SupervisedCodingPublicationService(
        preparation=StaticPreparation(
            PreparedCodingTask(
                task_id=TASK_ID,
                execution_id=EXECUTION_ID,
                change_set=change_set,
            )
        ),
        verification=StaticVerification(verified),
        publisher=StaticPublisher(
            VerifiedPublicationResult(
                reference="https://github.com/kersbaumerHugo/agent-platform/pull/123",
                identity=identify_change_set(different_change_set),
            )
        ),
        tracer=tracer,
    )

    with pytest.raises(CodingPublicationIdentityMismatchError):
        await service.execute(_task())

    spans = exporter.get_finished_spans()

    assert len(spans) == 1

    span = spans[0]

    assert span.name == "coding.supervised"
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes is not None

    assert span.attributes["agent_platform.coding.task.id"] == str(TASK_ID)
    assert span.attributes["agent_platform.coding.execution.id"] == str(EXECUTION_ID)
    assert (
        span.attributes["agent_platform.coding.change_set.identity"] == verified.identity.reference
    )
    assert span.attributes["error.type"] == "CodingPublicationIdentityMismatchError"
    assert "agent_platform.coding.publication.outcome" not in span.attributes

    assert any(event.name == "exception" for event in span.events)
