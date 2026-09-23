import sys
from uuid import uuid4

import pytest

from agent_platform.api.composition import (
    build_agent_tool_registry,
)
from agent_platform.domain.capability import CapabilityDefinition
from agent_platform.domain.coding import (
    CodingPublicationOutcome,
    CodingResult,
    CodingTask,
    CodingVerificationOutcome,
)
from agent_platform.domain.observability import ObservationEvent
from agent_platform.domain.tool import ToolRequest


class RecordingCodingCapability:
    def __init__(self) -> None:
        self.tasks: list[CodingTask] = []

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
        self.tasks.append(request)

        return CodingResult(
            task_id=request.task_id,
            execution_id=uuid4(),
            base_revision=request.expected_base_revision,
            change_set_identity=f"v1:sha256:{'b' * 64}",
            changed_paths=("src/example.py",),
            verification_profile_version="m12-v0",
            verification_outcome=CodingVerificationOutcome.PASS,
            publication_outcome=CodingPublicationOutcome.PUBLISHED,
            publication_reference=("https://github.com/kersbaumerHugo/agent-platform/pull/1"),
            pull_request_number=1,
        )


class NoopObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


def test_agent_tool_registry_exposes_repository_inspection(
    tmp_path,
) -> None:
    registry = build_agent_tool_registry(
        {
            "AGENT_PLATFORM_REPOSITORY_PATH": str(tmp_path),
            "AGENT_PLATFORM_REPOWISE_COMMAND": "python",
        },
        observer=NoopObserver(),
    )

    assert [definition.name for definition in registry.definitions()] == ["repository_inspect"]


def test_agent_tool_registry_accepts_custom_repowise_command(
    tmp_path,
) -> None:
    registry = build_agent_tool_registry(
        {
            "AGENT_PLATFORM_REPOSITORY_PATH": str(tmp_path),
            "AGENT_PLATFORM_REPOWISE_COMMAND": sys.executable,
        },
        observer=NoopObserver(),
    )

    assert [definition.name for definition in registry.definitions()] == ["repository_inspect"]


def test_agent_tool_registry_requires_repository_path() -> None:
    with pytest.raises(
        ValueError,
        match="AGENT_PLATFORM_REPOSITORY_PATH",
    ):
        build_agent_tool_registry(
            {},
            observer=NoopObserver(),
        )


def test_agent_tool_registry_rejects_missing_repository() -> None:
    with pytest.raises(
        ValueError,
        match="existing directory",
    ):
        build_agent_tool_registry(
            {
                "AGENT_PLATFORM_REPOSITORY_PATH": ("/definitely/not/a/repository"),
                "AGENT_PLATFORM_REPOWISE_COMMAND": "python",
            },
            observer=NoopObserver(),
        )


def test_agent_tool_registry_rejects_missing_repowise(
    tmp_path,
) -> None:
    with pytest.raises(
        ValueError,
        match="could not be resolved",
    ):
        build_agent_tool_registry(
            {
                "AGENT_PLATFORM_REPOSITORY_PATH": str(tmp_path),
                "AGENT_PLATFORM_REPOWISE_COMMAND": ("definitely-not-a-real-command"),
            },
            observer=NoopObserver(),
        )


def test_agent_tool_registry_rejects_blank_repowise_command(
    tmp_path,
) -> None:
    with pytest.raises(
        ValueError,
        match="AGENT_PLATFORM_REPOWISE_COMMAND",
    ):
        build_agent_tool_registry(
            {
                "AGENT_PLATFORM_REPOSITORY_PATH": str(tmp_path),
                "AGENT_PLATFORM_REPOWISE_COMMAND": "   ",
            },
            observer=NoopObserver(),
        )


def test_agent_tool_registry_exposes_coding_only_when_injected(
    tmp_path,
) -> None:
    capability = RecordingCodingCapability()

    registry = build_agent_tool_registry(
        {
            "AGENT_PLATFORM_REPOSITORY_PATH": str(tmp_path),
            "AGENT_PLATFORM_REPOWISE_COMMAND": "python",
        },
        observer=NoopObserver(),
        coding_capability=capability,
    )

    assert [definition.name for definition in registry.definitions()] == [
        "coding_execute",
        "repository_inspect",
    ]


@pytest.mark.asyncio
async def test_developer_agent_principal_can_invoke_injected_coding(
    tmp_path,
) -> None:
    capability = RecordingCodingCapability()

    registry = build_agent_tool_registry(
        {
            "AGENT_PLATFORM_REPOSITORY_PATH": str(tmp_path),
            "AGENT_PLATFORM_REPOWISE_COMMAND": "python",
        },
        observer=NoopObserver(),
        coding_capability=capability,
    )

    result = await registry.invoke(
        "coding_execute",
        ToolRequest(
            run_id=uuid4(),
            principal_id="agent:developer-agent",
            arguments={
                "goal": "Change one controlled file.",
                "expected_base_revision": "a" * 40,
            },
        ),
    )

    assert result.tool_name == "coding_execute"
    assert len(capability.tasks) == 1


@pytest.mark.asyncio
async def test_other_principal_cannot_invoke_injected_coding(
    tmp_path,
) -> None:
    capability = RecordingCodingCapability()

    registry = build_agent_tool_registry(
        {
            "AGENT_PLATFORM_REPOSITORY_PATH": str(tmp_path),
            "AGENT_PLATFORM_REPOWISE_COMMAND": "python",
        },
        observer=NoopObserver(),
        coding_capability=capability,
    )

    with pytest.raises(
        PermissionError,
        match="capability_not_granted",
    ):
        await registry.invoke(
            "coding_execute",
            ToolRequest(
                run_id=uuid4(),
                principal_id="agent:other-agent",
                arguments={
                    "goal": "Change one controlled file.",
                    "expected_base_revision": "a" * 40,
                },
            ),
        )

    assert capability.tasks == []
