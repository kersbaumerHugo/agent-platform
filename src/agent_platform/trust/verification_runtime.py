from __future__ import annotations

import argparse
import asyncio
import signal
from pathlib import Path

from agent_platform.trust.authoritative_verifier import (
    AuthoritativeVerifier,
)
from agent_platform.trust.sandbox_execution import (
    TrustedWorkspaceResolver,
)
from agent_platform.trust.verification_docker import (
    DockerVerificationConfig,
    DockerVerificationProcessRunner,
)
from agent_platform.trust.verification_executor import (
    ProfileVerificationExecutor,
)
from agent_platform.trust.verification_service import (
    TrustedVerificationHandler,
    UnixSocketVerificationServer,
)


def build_server(
    *,
    socket_path: Path,
    workspace_root: Path,
    runtime_root: Path,
    image: str,
) -> UnixSocketVerificationServer:
    verifier = AuthoritativeVerifier(
        executor=ProfileVerificationExecutor(
            runner=DockerVerificationProcessRunner(
                config=DockerVerificationConfig(
                    image=image,
                    runtime_root=runtime_root,
                )
            )
        )
    )

    return UnixSocketVerificationServer(
        socket_path=socket_path,
        handler=TrustedVerificationHandler(
            workspace_resolver=TrustedWorkspaceResolver(
                workspace_root=workspace_root,
            ),
            verifier=verifier,
        ),
    )


async def serve(
    *,
    socket_path: Path,
    workspace_root: Path,
    runtime_root: Path,
    image: str,
) -> None:
    server = build_server(
        socket_path=socket_path,
        workspace_root=workspace_root,
        runtime_root=runtime_root,
        image=image,
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
    parser = argparse.ArgumentParser(description="Agent Platform trusted verifier.")

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

    args = parser.parse_args()

    asyncio.run(
        serve(
            socket_path=args.socket,
            workspace_root=args.workspace_root,
            runtime_root=args.runtime_root,
            image=args.image,
        )
    )


if __name__ == "__main__":
    main()
