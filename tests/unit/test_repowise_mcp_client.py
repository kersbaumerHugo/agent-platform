import pytest

from agent_platform.adapters.repository.repowise_mcp import (
    RepoWiseMCPClient,
)

TARGET = "src/agent_platform/domain/tool.py"


def _structured_content(
    *,
    target_stale: bool = False,
    index_behind: bool = False,
) -> dict:
    return {
        "result": {
            "targets": {
                TARGET: {
                    "type": "file",
                    "path": TARGET,
                    "docs": {
                        "summary": ("Defines Agent Platform tool contracts."),
                        "symbols": [
                            {
                                "name": "ToolDefinition",
                                "kind": "class",
                                "signature": "class ToolDefinition",
                                "line": 7,
                                "symbol_id": ("src/agent_platform/domain/tool.py::ToolDefinition"),
                            },
                            {
                                "name": "ToolRequest",
                                "kind": "class",
                                "signature": "class ToolRequest",
                                "line": 15,
                                "symbol_id": ("src/agent_platform/domain/tool.py::ToolRequest"),
                            },
                        ],
                    },
                    "freshness": {
                        "is_stale": target_stale,
                    },
                }
            },
            "_meta": {
                "contract_version": 2,
                "indexed_commit": "ee2af373e39e",
                "live_head": "ee2af373e39e",
                "index_behind": index_behind,
            },
        }
    }


def test_parser_maps_real_repowise_context_contract() -> None:
    result = RepoWiseMCPClient._parse_context(
        _structured_content(),
        (TARGET,),
    )

    assert len(result.items) == 1
    assert result.items[0].target == TARGET
    assert result.items[0].summary == "Defines Agent Platform tool contracts."

    assert result.indexed_commit == "ee2af373e39e"
    assert result.stale is False
    assert len(result.items[0].symbols) == 2

    assert result.items[0].symbols[0].name == "ToolDefinition"
    assert result.items[0].symbols[0].kind == "class"
    assert result.items[0].symbols[0].signature == "class ToolDefinition"
    assert result.items[0].symbols[0].line == 7

    assert result.items[0].symbols[1].name == "ToolRequest"


@pytest.mark.parametrize(
    ("target_stale", "index_behind"),
    [
        (True, False),
        (False, True),
        (True, True),
    ],
)
def test_parser_preserves_repowise_stale_signals(
    target_stale: bool,
    index_behind: bool,
) -> None:
    result = RepoWiseMCPClient._parse_context(
        _structured_content(
            target_stale=target_stale,
            index_behind=index_behind,
        ),
        (TARGET,),
    )

    assert result.stale is True


def test_parser_fails_closed_when_target_is_missing() -> None:
    with pytest.raises(
        ValueError,
        match="response missing target",
    ):
        RepoWiseMCPClient._parse_context(
            {
                "result": {
                    "targets": {},
                    "_meta": {},
                }
            },
            (TARGET,),
        )


def test_parser_fails_closed_without_structured_content() -> None:
    with pytest.raises(
        ValueError,
        match="no structured content",
    ):
        RepoWiseMCPClient._parse_context(
            None,
            (TARGET,),
        )


def test_parser_fails_closed_without_summary() -> None:
    with pytest.raises(
        ValueError,
        match="has no summary",
    ):
        RepoWiseMCPClient._parse_context(
            {
                "result": {
                    "targets": {
                        TARGET: {
                            "docs": {
                                "symbols": [
                                    {
                                        "name": "ToolDefinition",
                                        "kind": "class",
                                        "signature": "class ToolDefinition",
                                        "line": 7,
                                        "symbol_id": (
                                            "src/agent_platform/domain/tool.py::ToolDefinition"
                                        ),
                                    },
                                    {
                                        "name": "ToolRequest",
                                        "kind": "class",
                                        "signature": "class ToolRequest",
                                        "line": 15,
                                        "symbol_id": (
                                            "src/agent_platform/domain/tool.py::ToolRequest"
                                        ),
                                    },
                                ],
                            },
                        }
                    },
                    "_meta": {},
                }
            },
            (TARGET,),
        )


def test_parser_allows_context_without_symbols() -> None:
    content = _structured_content()

    content["result"]["targets"][TARGET]["docs"]["symbols"] = []

    result = RepoWiseMCPClient._parse_context(
        content,
        (TARGET,),
    )

    assert result.items[0].symbols == ()
