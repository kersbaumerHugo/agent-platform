from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from agent_platform.adapters.capabilities.repository import (
    RepositoryInspectionCapability,
)
from agent_platform.adapters.runtimes.tool_calling import (
    ToolCallingRuntime,
)
from agent_platform.adapters.tools.repository import (
    RepositoryInspectionTool,
)
from agent_platform.application.capability_authorization import (
    StaticCapabilityAuthorizationPolicy,
)
from agent_platform.application.run_agent import RunAgent
from agent_platform.application.tool_registry import ToolRegistry
from agent_platform.domain.model import (
    MessageRole,
    ModelRequest,
    ModelResult,
    ModelToolCall,
)
from agent_platform.domain.models import (
    RunRequest,
    RunStatus,
)
from agent_platform.domain.observability import ObservationEvent
from agent_platform.domain.repository import (
    RepositoryEvidence,
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
)

TARGET = "src/agent_platform/domain/tool.py"
AGENT_ID = "developer-agent"
PRINCIPAL = "agent:developer-agent"


class NullObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


@dataclass
class RecordingRepositoryBackend:
    requests: list[RepositoryInspectionRequest] = field(default_factory=list)

    async def inspect(
        self,
        request: RepositoryInspectionRequest,
    ) -> RepositoryInspectionResult:
        self.requests.append(request)

        return RepositoryInspectionResult(
            evidence=(
                RepositoryEvidence(
                    target=request.targets[0],
                    summary="Defines the platform tool boundary.",
                    source_reference=(f"repowise:get_context:{request.targets[0]}"),
                ),
            ),
            indexed_revision="abcdef123456",
            stale=False,
        )


class ScriptedGateway:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        self.requests.append(request)

        if len(self.requests) == 1:
            return ModelResult(
                provider="test",
                model="tool-model",
                tool_calls=[
                    ModelToolCall(
                        id="call-1",
                        name="repository_inspect",
                        arguments=json.dumps(
                            {
                                "targets": [TARGET],
                            }
                        ),
                    )
                ],
                finish_reason="tool_calls",
            )

        return ModelResult(
            provider="test",
            model="tool-model",
            output="Repository inspection completed.",
            finish_reason="stop",
        )


@pytest.mark.asyncio
async def test_agent_executes_repository_capability_through_tool_runtime() -> None:
    backend = RecordingRepositoryBackend()

    capability = RepositoryInspectionCapability(backend)

    tool = RepositoryInspectionTool(
        capability,
        StaticCapabilityAuthorizationPolicy(
            grants=[
                (
                    PRINCIPAL,
                    "repository.inspect",
                )
            ]
        ),
    )

    registry = ToolRegistry(
        [tool],
        NullObserver(),
    )

    gateway = ScriptedGateway()

    runtime = ToolCallingRuntime(
        gateway=gateway,
        registry=registry,
        agent_id=AGENT_ID,
        principal_id=PRINCIPAL,
    )

    agent = RunAgent(
        runtime=runtime,
        observer=NullObserver(),
    )

    result = await agent.execute(
        RunRequest(
            agent_id="developer-agent",
            input="Inspect the platform tool boundary.",
        )
    )

    assert result.status is RunStatus.SUCCEEDED
    assert result.output == "Repository inspection completed."

    assert len(backend.requests) == 1
    assert backend.requests[0].targets == (TARGET,)

    assert len(gateway.requests) == 2

    first_request = gateway.requests[0]

    assert first_request.run_id == result.run_id
    assert first_request.max_tokens is None
    assert [tool.name for tool in first_request.tools] == ["repository_inspect"]

    final_request = gateway.requests[1]

    assert final_request.run_id == result.run_id
    assert final_request.tools == []
    assert final_request.max_tokens == 512

    assert [message.role for message in final_request.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]

    tool_message = final_request.messages[-1]

    assert tool_message.tool_call_id == "call-1"

    tool_output = json.loads(tool_message.content or "{}")

    assert tool_output["stale"] is False
    assert tool_output["evidence"][0]["target"] == TARGET


@pytest.mark.asyncio
async def test_agent_id_does_not_bypass_capability_authorization() -> None:
    backend = RecordingRepositoryBackend()

    capability = RepositoryInspectionCapability(backend)

    tool = RepositoryInspectionTool(
        capability,
        StaticCapabilityAuthorizationPolicy(
            grants=[
                (
                    "agent:privileged-name",
                    "repository.inspect",
                )
            ]
        ),
    )

    registry = ToolRegistry(
        [tool],
        NullObserver(),
    )

    runtime = ToolCallingRuntime(
        gateway=ScriptedGateway(),
        registry=registry,
        agent_id="privileged-name",
        principal_id="mcp:anonymous",
    )

    agent = RunAgent(
        runtime=runtime,
        observer=NullObserver(),
    )

    result = await agent.execute(
        RunRequest(
            agent_id="privileged-name",
            input="Inspect repository.",
        )
    )

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert "capability_not_granted" in result.error

    assert backend.requests == []


@pytest.mark.asyncio
async def test_runtime_rejects_agent_identity_mismatch() -> None:
    backend = RecordingRepositoryBackend()

    capability = RepositoryInspectionCapability(backend)

    tool = RepositoryInspectionTool(
        capability,
        StaticCapabilityAuthorizationPolicy(
            grants=[
                (
                    PRINCIPAL,
                    "repository.inspect",
                )
            ]
        ),
    )

    registry = ToolRegistry(
        [tool],
        NullObserver(),
    )

    gateway = ScriptedGateway()

    runtime = ToolCallingRuntime(
        gateway=gateway,
        registry=registry,
        agent_id=AGENT_ID,
        principal_id=PRINCIPAL,
    )

    agent = RunAgent(
        runtime=runtime,
        observer=NullObserver(),
    )

    result = await agent.execute(
        RunRequest(
            agent_id="other-agent",
            input="Inspect repository.",
        )
    )

    assert result.status is RunStatus.FAILED
    assert result.error == "agent_identity_mismatch"

    assert gateway.requests == []
    assert backend.requests == []
