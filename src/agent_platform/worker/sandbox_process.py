from __future__ import annotations

import argparse
import asyncio
import os
import sys
from functools import partial
from pathlib import Path

from agent_platform.adapters.workers.dsh import DshWorkerExecutor
from agent_platform.worker.session import WorkerExecutionRequest

_GATEWAY_HOST = "127.0.0.1"
_GATEWAY_PORT = 18080
_DSH_HOME = Path("/tmp/agent-platform-dsh")
_DSH_CONTEXT_PATCH = _DSH_HOME / "context-policy.patch.yml"

_COMPACTION_THRESHOLD_RATIO = 0.55
_COMPACTION_RETAIN_TOKENS = 1024
_COMPACTION_MAX_TOKENS = 768
_COMPACTION_RETRIES = 1
_MAX_OVERFLOW_RETRIES = 1


def _context_policy_patch(
    *,
    context_window: int,
    max_output_tokens: int,
) -> str:
    return (
        "- id: llm-deepseek\n"
        "  config:\n"
        "    apiKeyEnv: DEEPSEEK_API_KEY\n"
        f"    defaultContextWindow: {context_window}\n"
        f"    maxTokens: {max_output_tokens}\n"
        "    streamIdleTimeoutMs: 172800000\n"
        "\n"
        "- insert:\n"
        "    - id: token-meter\n"
        "      name: '@deepseek-ai/dsh-token-meter'\n"
        "\n"
        "    - id: compaction-basic\n"
        "      name: '@deepseek-ai/dsh-compaction-basic'\n"
        "      config:\n"
        f"        thresholdRatio: {_COMPACTION_THRESHOLD_RATIO}\n"
        f"        retainTokens: {_COMPACTION_RETAIN_TOKENS}\n"
        f"        maxTokens: {_COMPACTION_MAX_TOKENS}\n"
        f"        compactionRetries: {_COMPACTION_RETRIES}\n"
        f"        maxOverflowRetries: {_MAX_OVERFLOW_RETRIES}\n"
        "        auto: true\n"
    )


def _content_length(headers: bytes) -> int:
    decoded = headers.decode("iso-8859-1")
    lines = decoded.split("\r\n")

    for line in lines[1:]:
        name, separator, value = line.partition(":")

        if separator and name.strip().lower() == "content-length":
            length = int(value.strip())

            if length < 0:
                raise ValueError("Negative content length.")

            return length

    raise ValueError("Content-Length is required.")


async def _proxy_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    socket_path: Path,
) -> None:
    upstream_writer: asyncio.StreamWriter | None = None

    try:
        headers = await reader.readuntil(b"\r\n\r\n")

        if len(headers) > 64 * 1024:
            raise ValueError("Gateway request headers are too large.")

        body_length = _content_length(headers)

        if body_length > 8 * 1024 * 1024:
            raise ValueError("Gateway request body is too large.")

        body = await reader.readexactly(body_length)

        upstream_reader, upstream_writer = await asyncio.open_unix_connection(
            socket_path,
        )

        upstream_writer.write(headers)
        upstream_writer.write(body)
        await upstream_writer.drain()

        while True:
            chunk = await upstream_reader.read(64 * 1024)

            if not chunk:
                break

            writer.write(chunk)
            await writer.drain()

    finally:
        if upstream_writer is not None:
            upstream_writer.close()

            try:
                await upstream_writer.wait_closed()
            except (ConnectionError, OSError):
                pass

        writer.close()

        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()

    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")

    return value


async def _run(args: argparse.Namespace) -> int:
    goal = sys.stdin.read()

    if not goal.strip():
        raise RuntimeError("Sandbox coding process received an empty goal.")

    gateway_socket = Path(_required_env("AGENT_PLATFORM_GATEWAY_SOCKET"))

    _DSH_HOME.mkdir(
        parents=True,
        exist_ok=True,
    )

    _DSH_CONTEXT_PATCH.write_text(
        _context_policy_patch(
            context_window=args.context_window,
            max_output_tokens=args.max_output_tokens,
        ),
        encoding="utf-8",
    )

    server = await asyncio.start_server(
        partial(
            _proxy_request,
            socket_path=gateway_socket,
        ),
        host=_GATEWAY_HOST,
        port=_GATEWAY_PORT,
    )

    runtime_env = {
        "DEEPSEEK_BASE_URL": _required_env("DEEPSEEK_BASE_URL"),
        "DEEPSEEK_API_KEY": _required_env("DEEPSEEK_API_KEY"),
        "HOME": _required_env("HOME"),
        "TMPDIR": _required_env("TMPDIR"),
        "XDG_CACHE_HOME": _required_env("XDG_CACHE_HOME"),
        "DSH_CONTEXT_WINDOW": str(args.context_window),
    }

    executor = DshWorkerExecutor(
        dsh_home=_DSH_HOME,
        provider=args.provider,
        model=args.model,
        profile=args.profile,
        request_timeout_seconds=(args.request_timeout_seconds),
        patches=(_DSH_CONTEXT_PATCH,),
        env=runtime_env,
    )

    try:
        result = await executor.execute(
            WorkerExecutionRequest(
                goal=goal,
                workspace=Path.cwd(),
            )
        )
    finally:
        server.close()
        await server.wait_closed()

    sys.stdout.write(result.summary)

    if result.summary and not result.summary.endswith("\n"):
        sys.stdout.write("\n")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one coding Worker inside the trusted sandbox."
    )

    parser.add_argument(
        "--provider",
        required=True,
    )
    parser.add_argument(
        "--model",
        required=True,
    )
    parser.add_argument(
        "--profile",
        default="sdk-minimal",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=180.0,
    )
    parser.add_argument(
        "--context-window",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--max-output-tokens",
        required=True,
        type=int,
    )

    args = parser.parse_args()

    if args.request_timeout_seconds <= 0:
        parser.error("--request-timeout-seconds must be greater than zero")

    if args.context_window <= 0:
        parser.error("--context-window must be greater than zero")

    if args.max_output_tokens <= 0:
        parser.error("--max-output-tokens must be greater than zero")

    if args.max_output_tokens >= args.context_window:
        parser.error("--max-output-tokens must be smaller than --context-window")

    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
