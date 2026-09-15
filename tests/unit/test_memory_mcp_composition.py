from pathlib import Path

from agent_platform.api.mcp import (
    build_tool_registry,
)


def test_memory_tools_are_registered_when_configured(
    tmp_path: Path,
) -> None:
    registry = build_tool_registry(tmp_path / "memory.sqlite3")

    names = {definition.name for definition in registry.definitions()}

    assert names == {
        "diagnostic_echo",
        "memory_recall",
        "memory_remember",
    }
