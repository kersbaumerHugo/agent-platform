from __future__ import annotations

import argparse
import asyncio
import os
import signal
from pathlib import Path

from agent_platform.trust.docker_sandbox import (
    DockerSandboxBackend,
    DockerSandboxConfig,
)
from agent_platform.trust.sandbox_execution import (
    TrustedWorkspaceResolver,
)
from agent_platform.trust.sandbox_service import (
    TrustedSandboxExecutionHandler,
    UnixSocketSandboxServer,
)


def build_server(
    *,
    socket_path: Path,
    workspace_root: Path,
    runtime_root: Path,
    image: str,
    gateway_host: str,
    gateway_port: int,
    gateway_api_key: str,
    provider: str,
    model: str,
    profile: str = "sdk-minimal",
    request_timeout_seconds: float = 180.0,
    context_window: int,
    max_output_tokens: int,
) -> UnixSocketSandboxServer:
    if not provider.strip():
        raise ValueError("provider must not be blank.")

    if not model.strip():
        raise ValueError("model must not be blank.")

    if request_timeout_seconds <= 0:
        raise ValueError("request_timeout_seconds must be greater than zero.")

    if context_window <= 0:
        raise ValueError("context_window must be greater than zero.")

    if max_output_tokens <= 0:
        raise ValueError("max_output_tokens must be greater than zero.")

    if max_output_tokens >= context_window:
        raise ValueError("max_output_tokens must be smaller than context_window.")

    command = (
        "python",
        "-m",
        "agent_platform.worker.sandbox_process",
        "--provider",
        provider,
        "--model",
        model,
        "--profile",
        profile,
        "--request-timeout-seconds",
        str(request_timeout_seconds),
        "--context-window",
        str(context_window),
        "--max-output-tokens",
        str(max_output_tokens),
    )

    backend = DockerSandboxBackend(
        config=DockerSandboxConfig(
            image=image,
            command=command,
            runtime_root=runtime_root,
            gateway_upstream_host=gateway_host,
            gateway_upstream_port=gateway_port,
            gateway_api_key=gateway_api_key,
            hard_timeout_seconds=600.0,
            tmpfs_spec="/tmp:rw,exec,nosuid,nodev,size=64m",
        )
    )

    handler = TrustedSandboxExecutionHandler(
        workspace_resolver=TrustedWorkspaceResolver(
            workspace_root=workspace_root,
        ),
        backend=backend,
    )

    return UnixSocketSandboxServer(
        socket_path=socket_path,
        handler=handler,
    )


async def serve(
    *,
    socket_path: Path,
    workspace_root: Path,
    runtime_root: Path,
    image: str,
    gateway_host: str,
    gateway_port: int,
    gateway_api_key: str,
    provider: str,
    model: str,
    profile: str,
    request_timeout_seconds: float,
    context_window: int,
    max_output_tokens: int,
) -> None:
    server = build_server(
        socket_path=socket_path,
        workspace_root=workspace_root,
        runtime_root=runtime_root,
        image=image,
        gateway_host=gateway_host,
        gateway_port=gateway_port,
        gateway_api_key=gateway_api_key,
        provider=provider,
        model=model,
        profile=profile,
        request_timeout_seconds=request_timeout_seconds,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (
        signal.SIGINT,
        signal.SIGTERM,
    ):
        loop.add_signal_handler(
            sig,
            stop_event.set,
        )

    await server.start()

    try:
        await stop_event.wait()
    finally:
        await server.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Platform trusted coding sandbox.")

    parser.add_argument(
        "--socket",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--workspace-root",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--runtime-root",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--image",
        required=True,
    )
    parser.add_argument(
        "--gateway-host",
        default="127.0.0.1",
    )
    parser.add_argument(
        "--gateway-port",
        type=int,
        default=8000,
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

    gateway_api_key = os.environ.get(
        "MODEL_GATEWAY_API_KEY",
        "",
    ).strip()

    if not gateway_api_key:
        raise RuntimeError("MODEL_GATEWAY_API_KEY is required.")

    asyncio.run(
        serve(
            socket_path=args.socket,
            workspace_root=args.workspace_root,
            runtime_root=args.runtime_root,
            image=args.image,
            gateway_host=args.gateway_host,
            gateway_port=args.gateway_port,
            gateway_api_key=gateway_api_key,
            provider=args.provider,
            model=args.model,
            profile=args.profile,
            request_timeout_seconds=(args.request_timeout_seconds),
            context_window=args.context_window,
            max_output_tokens=args.max_output_tokens,
        )
    )


if __name__ == "__main__":
    main()
