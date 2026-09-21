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
    }

    executor = DshWorkerExecutor(
        dsh_home=_DSH_HOME,
        provider=args.provider,
        model=args.model,
        profile=args.profile,
        request_timeout_seconds=(args.request_timeout_seconds),
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

    args = parser.parse_args()

    if args.request_timeout_seconds <= 0:
        parser.error("--request-timeout-seconds must be greater than zero")

    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
