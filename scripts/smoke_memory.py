import argparse
import asyncio
import json
import os
from typing import Any
from uuid import uuid4

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

DEFAULT_MCP_URL = "http://127.0.0.1:8001/mcp"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Smoke-test Agent Platform memory capabilities through MCP."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get(
            "AGENT_PLATFORM_MCP_URL",
            DEFAULT_MCP_URL,
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    remember = subparsers.add_parser("remember")
    remember.add_argument("--namespace", required=True)
    remember.add_argument("--content", required=True)

    recall = subparsers.add_parser("recall")
    recall.add_argument("--namespace", required=True)
    recall.add_argument("--query", required=True)
    recall.add_argument(
        "--expect",
        choices=("accept", "abstain"),
        default="accept",
    )
    recall.add_argument("--expect-content")

    return parser


async def call_tool(
    *,
    url: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[str, bool, dict[str, Any] | None]:
    run_id = uuid4()

    async with httpx2.AsyncClient(
        headers={
            "X-Agent-Platform-Run-Id": str(run_id),
        }
    ) as http_client:
        transport = streamable_http_client(
            url,
            http_client=http_client,
        )

        async with Client(transport) as client:
            result = await client.call_tool(
                tool_name,
                arguments,
            )

    return (
        str(run_id),
        bool(result.is_error),
        result.structured_content,
    )


async def main() -> None:
    args = build_parser().parse_args()

    if args.command == "remember":
        run_id, is_error, output = await call_tool(
            url=args.url,
            tool_name="memory_remember",
            arguments={
                "namespace": args.namespace,
                "content": args.content,
                "metadata": {
                    "source": "smoke_memory",
                },
            },
        )

        print(f"run_id: {run_id}")
        print(f"is_error: {is_error}")
        print(
            "output:",
            json.dumps(
                output,
                sort_keys=True,
            ),
        )

        if is_error:
            raise SystemExit(1)

        return

    run_id, is_error, output = await call_tool(
        url=args.url,
        tool_name="memory_recall",
        arguments={
            "namespace": args.namespace,
            "query": args.query,
        },
    )

    print(f"run_id: {run_id}")
    print(f"is_error: {is_error}")
    print(
        "output:",
        json.dumps(
            output,
            sort_keys=True,
        ),
    )

    if is_error or output is None:
        raise SystemExit(1)

    decision = output.get("decision")

    if decision != args.expect:
        raise RuntimeError(f"Expected decision {args.expect!r}, got {decision!r}.")

    if args.expect_content is not None:
        memories = output.get("memories", [])

        if not any(memory.get("content") == args.expect_content for memory in memories):
            raise RuntimeError("Expected memory content was not recalled.")


if __name__ == "__main__":
    asyncio.run(main())
