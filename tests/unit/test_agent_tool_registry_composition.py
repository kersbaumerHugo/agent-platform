import sys

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
