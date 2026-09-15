from pathlib import Path
from uuid import uuid4

import pytest
from mcp import Client

from agent_platform.adapters.mcp.server import (
    build_mcp_tool_server,
)
from agent_platform.adapters.memory.sqlite import (
    SQLiteFTSRetrieval,
    SQLiteMemoryStore,
)
from agent_platform.adapters.tools.memory import (
    MemoryRecallTool,
    MemoryRememberTool,
)
from agent_platform.application.retrieval_acceptance import (
    LexicalRetrievalAcceptanceGate,
)
from agent_platform.application.tool_registry import (
    ToolRegistry,
)
from agent_platform.domain.observability import (
    ObservationEvent,
)


class NullObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        pass


@pytest.mark.asyncio
async def test_memory_roundtrip_through_mcp(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.sqlite3"

    store = SQLiteMemoryStore(database_path)
    retrieval = SQLiteFTSRetrieval(database_path)
    acceptance = LexicalRetrievalAcceptanceGate()

    registry = ToolRegistry(
        [
            MemoryRememberTool(store),
            MemoryRecallTool(
                retrieval,
                acceptance,
            ),
        ],
        NullObserver(),
    )

    run_id = uuid4()

    server = build_mcp_tool_server(
        registry,
        run_id_resolver=lambda _: run_id,
    )

    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        remember = await client.call_tool(
            "memory_remember",
            {
                "namespace": "agent",
                "content": ("The local inference backend uses llama.cpp."),
                "metadata": {
                    "source": "mcp-test",
                },
            },
        )

        assert remember.is_error is False

        recall = await client.call_tool(
            "memory_recall",
            {
                "namespace": "agent",
                "query": "local inference",
            },
        )

    assert recall.is_error is False
    assert recall.structured_content is not None

    output = recall.structured_content

    assert output["decision"] == "accept"
    assert len(output["memories"]) == 1

    memory = output["memories"][0]

    assert memory["content"] == "The local inference backend uses llama.cpp."
    assert memory["metadata"] == {
        "source": "mcp-test",
    }
