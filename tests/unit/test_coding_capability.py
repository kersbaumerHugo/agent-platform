from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import pytest

from agent_platform.adapters.capabilities.coding import (
    SupervisedCodingCapability,
)
from agent_platform.contracts.capability import CapabilityContract
from agent_platform.domain.coding import (
    CodingPublicationOutcome,
    CodingResult,
    CodingTask,
    CodingVerificationOutcome,
)

TASK_ID = UUID("13000000-0000-4000-8000-000000000001")
EXECUTION_ID = UUID("13000000-0000-4000-8000-000000000002")
BASE_REVISION = "a" * 40
CHANGE_SET_IDENTITY = f"v1:sha256:{'b' * 64}"


def _task() -> CodingTask:
    return CodingTask(
        task_id=TASK_ID,
        goal="Change one controlled file.",
        expected_base_revision=BASE_REVISION,
    )


def _result() -> CodingResult:
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


@dataclass
class RecordingCodingService:
    result: CodingResult
    tasks: list[CodingTask] = field(default_factory=list)

    async def execute(
        self,
        task: CodingTask,
    ) -> CodingResult:
        self.tasks.append(task)
        return self.result


@pytest.mark.asyncio
async def test_coding_capability_exposes_stable_definition() -> None:
    service = RecordingCodingService(result=_result())

    capability: CapabilityContract[CodingTask, CodingResult] = SupervisedCodingCapability(service)

    assert capability.definition.name == "coding.execute"
    assert capability.definition.description


@pytest.mark.asyncio
async def test_coding_capability_delegates_typed_task_and_result() -> None:
    task = _task()
    expected = _result()
    service = RecordingCodingService(result=expected)

    capability = SupervisedCodingCapability(service)

    result = await capability.invoke(task)

    assert service.tasks == [task]
    assert result is expected
    assert result.task_id == TASK_ID
    assert result.execution_id == EXECUTION_ID


@pytest.mark.asyncio
async def test_coding_capability_does_not_translate_platform_contracts() -> None:
    task = _task()
    expected = _result()

    capability = SupervisedCodingCapability(RecordingCodingService(result=expected))

    result = await capability.invoke(task)

    assert isinstance(result, CodingResult)
    assert result == expected
