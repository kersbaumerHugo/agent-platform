import pytest

from agent_platform.api.composition import (
    build_agent_tool_registry,
)
from agent_platform.domain.observability import ObservationEvent


class NoopObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


def test_agent_tool_registry_exposes_repository_inspection() -> None:
    registry = build_agent_tool_registry(
        {
            "AGENT_PLATFORM_REPOSITORY_PATH": "/tmp/repository",
        },
        observer=NoopObserver(),
    )

    definitions = registry.definitions()

    assert [definition.name for definition in definitions] == [
        "repository_inspect",
    ]


def test_agent_tool_registry_accepts_custom_repowise_command() -> None:
    registry = build_agent_tool_registry(
        {
            "AGENT_PLATFORM_REPOSITORY_PATH": "/tmp/repository",
            "AGENT_PLATFORM_REPOWISE_COMMAND": ("/opt/repowise/bin/repowise"),
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


def test_agent_tool_registry_rejects_blank_repowise_command() -> None:
    with pytest.raises(
        ValueError,
        match="AGENT_PLATFORM_REPOWISE_COMMAND",
    ):
        build_agent_tool_registry(
            {
                "AGENT_PLATFORM_REPOSITORY_PATH": "/tmp/repository",
                "AGENT_PLATFORM_REPOWISE_COMMAND": "   ",
            },
            observer=NoopObserver(),
        )
