from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import pytest
from pydantic import ValidationError

from agent_platform.adapters.tools.coding import CodingTool
from agent_platform.domain.coding import (
    CodingPublicationOutcome,
    CodingResult,
    CodingTask,
    CodingVerificationOutcome,
)
from agent_platform.domain.tool import ToolRequest

RUN_ID = UUID("13000000-0000-4000-8000-000000000010")
TASK_ID = UUID("13000000-0000-4000-8000-000000000011")
EXECUTION_ID = UUID("13000000-0000-4000-8000-000000000012")
BASE_REVISION = "a" * 40
CHANGE_SET_IDENTITY = f"v1:sha256:{'b' * 64}"


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
class RecordingCodingCapability:
    result: CodingResult
    requests: list[CodingTask] = field(default_factory=list)

    async def invoke(
        self,
        request: CodingTask,
    ) -> CodingResult:
        self.requests.append(request)
        return self.result


def test_coding_tool_exposes_model_facing_contract() -> None:
    tool = CodingTool(RecordingCodingCapability(result=_result()))

    definition = tool.definition

    assert definition.name == "coding_execute"
    assert set(definition.input_schema["properties"]) == {
        "goal",
        "expected_base_revision",
    }
    assert "task_id" not in definition.input_schema["properties"]

    assert "task_id" in definition.output_schema["properties"]
    assert "execution_id" in definition.output_schema["properties"]


@pytest.mark.asyncio
async def test_coding_tool_translates_json_to_typed_capability() -> None:
    expected = _result()
    capability = RecordingCodingCapability(result=expected)
    tool = CodingTool(capability)

    result = await tool.invoke(
        ToolRequest(
            run_id=RUN_ID,
            arguments={
                "goal": "Change one controlled file.",
                "expected_base_revision": BASE_REVISION,
            },
        )
    )

    assert len(capability.requests) == 1

    task = capability.requests[0]

    assert isinstance(task, CodingTask)
    assert task.goal == "Change one controlled file."
    assert task.expected_base_revision == BASE_REVISION

    assert result.run_id == RUN_ID
    assert result.tool_name == "coding_execute"
    assert result.output == expected.model_dump(mode="json")


@pytest.mark.asyncio
async def test_coding_tool_rejects_extra_model_arguments() -> None:
    tool = CodingTool(RecordingCodingCapability(result=_result()))

    with pytest.raises(ValidationError):
        await tool.invoke(
            ToolRequest(
                run_id=RUN_ID,
                arguments={
                    "goal": "Change one controlled file.",
                    "expected_base_revision": BASE_REVISION,
                    "task_id": str(TASK_ID),
                },
            )
        )
