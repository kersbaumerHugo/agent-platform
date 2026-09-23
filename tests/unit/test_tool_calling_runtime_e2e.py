from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import UUID

import pytest

from agent_platform.adapters.capabilities.repository import (
    RepositoryInspectionCapability,
)
from agent_platform.adapters.runtimes.tool_calling import (
    ToolCallingRuntime,
)
from agent_platform.adapters.tools.coding import CodingTool
from agent_platform.adapters.tools.repository import (
    RepositoryInspectionTool,
)
from agent_platform.application.capability_authorization import (
    StaticCapabilityAuthorizationPolicy,
)
from agent_platform.application.run_agent import RunAgent
from agent_platform.application.tool_registry import ToolRegistry
from agent_platform.domain.capability import CapabilityDefinition
from agent_platform.domain.coding import (
    CodingPublicationOutcome,
    CodingResult,
    CodingTask,
    CodingVerificationOutcome,
)
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
INDEXED_REVISION = "a" * 40
EXECUTION_ID = UUID("15000000-0000-4000-8000-000000000001")
CHANGE_SET_IDENTITY = f"v1:sha256:{'b' * 64}"


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
            indexed_revision=INDEXED_REVISION,
            stale=False,
        )


@dataclass
class RecordingCodingCapability:
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
            task_id=request.task_id,
            execution_id=EXECUTION_ID,
            base_revision=request.expected_base_revision,
            change_set_identity=CHANGE_SET_IDENTITY,
            changed_paths=("README.md",),
            verification_profile_version="m12-v0",
            verification_outcome=CodingVerificationOutcome.PASS,
            publication_outcome=CodingPublicationOutcome.PUBLISHED,
            publication_reference=("https://github.com/kersbaumerHugo/agent-platform/pull/999"),
            pull_request_number=999,
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


class InspectThenCodeGateway:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []
        self.observed_revision: str | None = None

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
                        id="inspect-1",
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

        if len(self.requests) == 2:
            tool_message = request.messages[-1]
            assert tool_message.role is MessageRole.TOOL

            tool_output = json.loads(tool_message.content or "{}")
            self.observed_revision = tool_output["indexed_revision"]

            return ModelResult(
                provider="test",
                model="tool-model",
                tool_calls=[
                    ModelToolCall(
                        id="coding-1",
                        name="coding_execute",
                        arguments=json.dumps(
                            {
                                "goal": "Update README.md with one supervised change.",
                                "expected_base_revision": self.observed_revision,
                            }
                        ),
                    )
                ],
                finish_reason="tool_calls",
            )

        return ModelResult(
            provider="test",
            model="tool-model",
            output="Inspected, coded, verified, and published.",
            finish_reason="stop",
        )


class ExceedingGateway:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        self.requests.append(request)
        index = len(self.requests)

        if index <= 2:
            return ModelResult(
                provider="test",
                model="tool-model",
                tool_calls=[
                    ModelToolCall(
                        id=f"inspect-{index}",
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

        assert request.tools == []
        assert request.max_tokens == 512

        return ModelResult(
            provider="test",
            model="tool-model",
            tool_calls=[
                ModelToolCall(
                    id="inspect-3",
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


def _repository_tool(
    backend: RecordingRepositoryBackend,
    *,
    grants: list[tuple[str, str]] | None = None,
) -> RepositoryInspectionTool:
    capability = RepositoryInspectionCapability(backend)

    return RepositoryInspectionTool(
        capability,
        StaticCapabilityAuthorizationPolicy(
            grants=grants
            if grants is not None
            else [
                (
                    PRINCIPAL,
                    "repository.inspect",
                )
            ]
        ),
    )


@pytest.mark.asyncio
async def test_agent_executes_repository_capability_through_tool_runtime() -> None:
    backend = RecordingRepositoryBackend()

    registry = ToolRegistry(
        [_repository_tool(backend)],
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

    second_request = gateway.requests[1]

    assert second_request.run_id == result.run_id
    assert second_request.max_tokens is None
    assert [tool.name for tool in second_request.tools] == ["repository_inspect"]

    assert [message.role for message in second_request.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]

    tool_message = second_request.messages[-1]

    assert tool_message.tool_call_id == "call-1"

    tool_output = json.loads(tool_message.content or "{}")

    assert tool_output["stale"] is False
    assert tool_output["indexed_revision"] == INDEXED_REVISION
    assert tool_output["evidence"][0]["target"] == TARGET


@pytest.mark.asyncio
async def test_runtime_supports_inspect_then_coding_then_final_response() -> None:
    repository_backend = RecordingRepositoryBackend()
    coding_capability = RecordingCodingCapability()

    authorization = StaticCapabilityAuthorizationPolicy(
        grants=[
            (
                PRINCIPAL,
                "repository.inspect",
            ),
            (
                PRINCIPAL,
                "coding.execute",
            ),
        ]
    )

    registry = ToolRegistry(
        [
            RepositoryInspectionTool(
                RepositoryInspectionCapability(repository_backend),
                authorization,
            ),
            CodingTool(
                coding_capability,
                authorization,
            ),
        ],
        NullObserver(),
    )

    gateway = InspectThenCodeGateway()

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
            agent_id=AGENT_ID,
            input=(
                "Inspect the repository, determine the exact base revision, "
                "then make one supervised README change."
            ),
        )
    )

    assert result.status is RunStatus.SUCCEEDED
    assert result.output == "Inspected, coded, verified, and published."

    assert gateway.observed_revision == INDEXED_REVISION

    assert len(repository_backend.requests) == 1
    assert len(coding_capability.requests) == 1
    assert coding_capability.requests[0].expected_base_revision == INDEXED_REVISION

    assert len(gateway.requests) == 3

    first_request, second_request, final_request = gateway.requests

    assert [tool.name for tool in first_request.tools] == [
        "coding_execute",
        "repository_inspect",
    ]
    assert [tool.name for tool in second_request.tools] == [
        "coding_execute",
        "repository_inspect",
    ]

    assert final_request.tools == []
    assert final_request.max_tokens == 512

    assert [message.role for message in final_request.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]

    inspect_output = json.loads(final_request.messages[2].content or "{}")
    coding_output = json.loads(final_request.messages[4].content or "{}")

    assert inspect_output["indexed_revision"] == INDEXED_REVISION
    assert coding_output["base_revision"] == INDEXED_REVISION
    assert coding_output["publication_outcome"] == "published"


@pytest.mark.asyncio
async def test_runtime_fails_closed_after_two_tool_rounds() -> None:
    backend = RecordingRepositoryBackend()
    gateway = ExceedingGateway()

    runtime = ToolCallingRuntime(
        gateway=gateway,
        registry=ToolRegistry(
            [_repository_tool(backend)],
            NullObserver(),
        ),
        agent_id=AGENT_ID,
        principal_id=PRINCIPAL,
    )

    agent = RunAgent(
        runtime=runtime,
        observer=NullObserver(),
    )

    result = await agent.execute(
        RunRequest(
            agent_id=AGENT_ID,
            input="Keep inspecting forever.",
        )
    )

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert "two-round tool-call limit" in result.error

    assert len(backend.requests) == 2
    assert len(gateway.requests) == 3
    assert gateway.requests[-1].tools == []


@pytest.mark.asyncio
async def test_agent_id_does_not_bypass_capability_authorization() -> None:
    backend = RecordingRepositoryBackend()

    registry = ToolRegistry(
        [
            _repository_tool(
                backend,
                grants=[
                    (
                        "agent:privileged-name",
                        "repository.inspect",
                    )
                ],
            )
        ],
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
    gateway = ScriptedGateway()

    runtime = ToolCallingRuntime(
        gateway=gateway,
        registry=ToolRegistry(
            [_repository_tool(backend)],
            NullObserver(),
        ),
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
