from __future__ import annotations

import argparse
import asyncio
import signal
from pathlib import Path

from agent_platform.adapters.git.local import LocalGitChangeSink
from agent_platform.trust.change_policy import ChangePolicy
from agent_platform.trust.publisher import TrustedPublisher
from agent_platform.trust.service import (
    TrustedChangeHandler,
    UnixSocketChangeServer,
)


def build_server(
    *,
    socket_path: Path,
    repo_root: Path,
) -> UnixSocketChangeServer:
    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=LocalGitChangeSink(repo_root),
    )

    return UnixSocketChangeServer(
        socket_path=socket_path,
        handler=TrustedChangeHandler(publisher),
    )


async def serve(
    *,
    socket_path: Path,
    repo_root: Path,
) -> None:
    server = build_server(
        socket_path=socket_path,
        repo_root=repo_root,
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
    parser = argparse.ArgumentParser(description="Agent Platform trusted change publisher.")

    parser.add_argument(
        "--socket",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--repo",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    asyncio.run(
        serve(
            socket_path=args.socket,
            repo_root=args.repo,
        )
    )


if __name__ == "__main__":
    main()
