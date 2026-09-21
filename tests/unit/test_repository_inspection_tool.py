from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from agent_platform.adapters.tools.repository import (
    RepositoryInspectionTool,
)
from agent_platform.application.capability_authorization import (
    StaticCapabilityAuthorizationPolicy,
)
from agent_platform.domain.capability import CapabilityDefinition
from agent_platform.domain.repository import (
    RepositoryEvidence,
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
)
from agent_platform.domain.tool import ToolRequest


@dataclass
class RecordingRepositoryCapability:
    requests: list[RepositoryInspectionRequest] = field(default_factory=list)

    @property
    def definition(self) -> CapabilityDefinition:
        return CapabilityDefinition(
            name="repository.inspect",
            description="Inspect repository evidence.",
        )

    async def invoke(
        self,
        request: RepositoryInspectionRequest,
    ) -> RepositoryInspectionResult:
        self.requests.append(request)

        return RepositoryInspectionResult(
            evidence=(
                RepositoryEvidence(
                    target=request.targets[0],
                    summary="Repository evidence.",
                    source_reference="repowise:get_context",
                ),
            ),
            indexed_revision="abcdef123456",
            stale=False,
        )


def _authorization() -> StaticCapabilityAuthorizationPolicy:
    return StaticCapabilityAuthorizationPolicy(
        grants=[
            (
                "agent:developer",
                "repository.inspect",
            )
        ]
    )


@pytest.mark.asyncio
async def test_repository_tool_invokes_typed_capability() -> None:
    capability = RecordingRepositoryCapability()

    tool = RepositoryInspectionTool(
        capability,
        _authorization(),
    )

    run_id = uuid4()

    result = await tool.invoke(
        ToolRequest(
            run_id=run_id,
            principal_id="agent:developer",
            arguments={
                "targets": [
                    "src/agent_platform/domain/tool.py",
                ]
            },
        )
    )

    assert len(capability.requests) == 1
    assert capability.requests[0].targets == ("src/agent_platform/domain/tool.py",)

    assert result.run_id == run_id
    assert result.tool_name == "repository_inspect"
    assert result.output["stale"] is False


@pytest.mark.asyncio
async def test_repository_tool_denies_ungranted_principal() -> None:
    capability = RecordingRepositoryCapability()

    tool = RepositoryInspectionTool(
        capability,
        StaticCapabilityAuthorizationPolicy(),
    )

    with pytest.raises(
        PermissionError,
        match="capability_not_granted",
    ):
        await tool.invoke(
            ToolRequest(
                run_id=uuid4(),
                principal_id="mcp:anonymous",
                arguments={
                    "targets": [
                        "src/agent_platform/domain/tool.py",
                    ]
                },
            )
        )

    assert capability.requests == []


def test_repository_tool_exposes_model_facing_contract() -> None:
    tool = RepositoryInspectionTool(
        RecordingRepositoryCapability(),
        _authorization(),
    )

    assert tool.definition.name == "repository_inspect"
    assert "targets" in tool.definition.input_schema["properties"]
    assert "evidence" in tool.definition.output_schema["properties"]
