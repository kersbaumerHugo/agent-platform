import asyncio
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent_platform.contracts.repowise import (
    RepoWiseContextItem,
    RepoWiseContextSnapshot,
    RepoWiseSymbol,
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

        snapshot = self._parse_context(
            result.structured_content,
            targets,
        )

        if snapshot.indexed_commit is None:
            return snapshot

        full_revision = await self._resolve_full_git_revision(
            snapshot.indexed_commit,
        )

        return snapshot.model_copy(
            update={
                "indexed_commit": full_revision,
            }
        )

    async def _resolve_full_git_revision(
        self,
        revision: str,
    ) -> str:
        process = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--verify",
            f"{revision}^{{commit}}",
            cwd=self._repository_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()

        if process.returncode != 0:
            raise ValueError("RepoWise indexed commit could not be resolved in the repository.")

        resolved = stdout.decode("utf-8").strip().lower()

        if len(resolved) != 40 or any(
            character not in "0123456789abcdef" for character in resolved
        ):
            raise ValueError(
                "RepoWise indexed commit did not resolve to a full 40-character Git SHA-1."
            )

        return resolved

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

            raw_symbols = docs.get("symbols", [])

            if not isinstance(raw_symbols, list):
                raise ValueError(f"RepoWise target has invalid symbols: {target}")

            symbols: list[RepoWiseSymbol] = []

            for raw_symbol in raw_symbols:
                if not isinstance(raw_symbol, dict):
                    raise ValueError(f"RepoWise target has invalid symbol: {target}")

                name = raw_symbol.get("name")
                kind = raw_symbol.get("kind")
                signature = raw_symbol.get("signature")
                line = raw_symbol.get("line")

                if not isinstance(name, str) or not name.strip():
                    raise ValueError(f"RepoWise symbol has no name: {target}")

                if not isinstance(kind, str) or not kind.strip():
                    raise ValueError(f"RepoWise symbol has no kind: {target}")

                if not isinstance(signature, str) or not signature.strip():
                    raise ValueError(f"RepoWise symbol has no signature: {target}")

                if line is not None and (
                    not isinstance(line, int) or isinstance(line, bool) or line < 1
                ):
                    raise ValueError(f"RepoWise symbol has invalid line: {target}")

                symbols.append(
                    RepoWiseSymbol(
                        name=name.strip(),
                        kind=kind.strip(),
                        signature=signature.strip(),
                        line=line,
                    )
                )

            freshness = raw_target.get("freshness")

            if isinstance(freshness, dict) and freshness.get("is_stale") is True:
                stale = True

            items.append(
                RepoWiseContextItem(
                    target=target,
                    summary=summary.strip(),
                    symbols=tuple(symbols),
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
