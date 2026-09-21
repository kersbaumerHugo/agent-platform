from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent_platform.contracts.repowise import (
    RepoWiseContextItem,
    RepoWiseContextSnapshot,
)


class RepoWiseMCPClient:
    """Read repository context from RepoWise through MCP stdio."""

    def __init__(
        self,
        repository_path: str | Path,
        *,
        command: str = "repowise",
    ) -> None:
        self._repository_path = Path(repository_path)
        self._command = command

    async def get_context(
        self,
        targets: tuple[str, ...],
    ) -> RepoWiseContextSnapshot:
        server = StdioServerParameters(
            command=self._command,
            args=["mcp"],
            cwd=self._repository_path,
        )

        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "get_context",
                    arguments={
                        "targets": list(targets),
                    },
                )

        if result.is_error:
            raise RuntimeError("RepoWise get_context returned an MCP error.")

        return self._parse_context(
            result.structured_content,
            targets,
        )

    @staticmethod
    def _parse_context(
        structured_content: dict[str, Any] | None,
        requested_targets: tuple[str, ...],
    ) -> RepoWiseContextSnapshot:
        if structured_content is None:
            raise ValueError("RepoWise get_context returned no structured content.")

        raw_result = structured_content.get("result")

        if not isinstance(raw_result, dict):
            raise ValueError("RepoWise get_context returned no result object.")

        raw_targets = raw_result.get("targets")

        if not isinstance(raw_targets, dict):
            raise ValueError("RepoWise get_context returned no targets object.")

        items: list[RepoWiseContextItem] = []
        stale = False

        for target in requested_targets:
            raw_target = raw_targets.get(target)

            if not isinstance(raw_target, dict):
                raise ValueError(f"RepoWise response missing target: {target}")

            docs = raw_target.get("docs")

            if not isinstance(docs, dict):
                raise ValueError(f"RepoWise target has no docs: {target}")

            summary = docs.get("summary")

            if not isinstance(summary, str) or not summary.strip():
                raise ValueError(f"RepoWise target has no summary: {target}")

            freshness = raw_target.get("freshness")

            if isinstance(freshness, dict) and freshness.get("is_stale") is True:
                stale = True

            items.append(
                RepoWiseContextItem(
                    target=target,
                    summary=summary.strip(),
                )
            )

        indexed_commit: str | None = None

        raw_meta = raw_result.get("_meta")

        if isinstance(raw_meta, dict):
            raw_indexed_commit = raw_meta.get("indexed_commit")

            if isinstance(raw_indexed_commit, str) and raw_indexed_commit.strip():
                indexed_commit = raw_indexed_commit.strip()

            if raw_meta.get("index_behind") is True:
                stale = True

        return RepoWiseContextSnapshot(
            items=tuple(items),
            indexed_commit=indexed_commit,
            stale=stale,
        )
