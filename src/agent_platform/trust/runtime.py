from __future__ import annotations

import argparse
import asyncio
import signal
from pathlib import Path

from agent_platform.adapters.git.disposable import (
    DisposableGitRemoteChangeSink,
)
from agent_platform.adapters.git.local import LocalGitChangeSink
from agent_platform.adapters.github.cli import GitHubCliPullRequestClient
from agent_platform.adapters.github.proposal import PullRequestChangeSink
from agent_platform.trust.change_policy import ChangePolicy
from agent_platform.trust.publisher import ChangeSink, TrustedPublisher
from agent_platform.trust.service import (
    TrustedChangeHandler,
    UnixSocketChangeServer,
)


def build_server(
    *,
    socket_path: Path,
    repo_root: Path,
    sink: ChangeSink | None = None,
) -> UnixSocketChangeServer:
    publication_sink = sink or LocalGitChangeSink(repo_root)

    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=publication_sink,
    )

    return UnixSocketChangeServer(
        socket_path=socket_path,
        handler=TrustedChangeHandler(publisher),
    )


def build_github_server(
    *,
    socket_path: Path,
    repository_url: str,
    workspace_parent: Path,
    repository: str,
    remote_name: str = "origin",
    base_branch: str = "main",
    gh_binary: str = "gh",
) -> UnixSocketChangeServer:
    git_sink = DisposableGitRemoteChangeSink(
        repository_url=repository_url,
        workspace_parent=workspace_parent,
        remote_name=remote_name,
        base_branch=base_branch,
    )

    pr_client = GitHubCliPullRequestClient(
        repository,
        gh_binary=gh_binary,
    )

    proposal_sink = PullRequestChangeSink(
        git_sink=git_sink,
        pr_client=pr_client,
        base_branch=base_branch,
    )

    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=proposal_sink,
    )

    return UnixSocketChangeServer(
        socket_path=socket_path,
        handler=TrustedChangeHandler(publisher),
    )


async def serve(
    *,
    socket_path: Path,
    repo_root: Path | None = None,
    github_repository: str | None = None,
    repository_url: str | None = None,
    workspace_parent: Path | None = None,
    remote_name: str = "origin",
    base_branch: str = "main",
    gh_binary: str = "gh",
) -> None:
    if github_repository is None:
        if repo_root is None:
            raise ValueError("repo_root is required for local publication.")

        server = build_server(
            socket_path=socket_path,
            repo_root=repo_root,
        )
    else:
        if repository_url is None:
            raise ValueError("repository_url is required for GitHub publication.")

        if workspace_parent is None:
            raise ValueError("workspace_parent is required for GitHub publication.")

        server = build_github_server(
            socket_path=socket_path,
            repository_url=repository_url,
            workspace_parent=workspace_parent,
            repository=github_repository,
            remote_name=remote_name,
            base_branch=base_branch,
            gh_binary=gh_binary,
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
        type=Path,
    )

    parser.add_argument(
        "--github-repository",
    )

    parser.add_argument(
        "--repository-url",
    )

    parser.add_argument(
        "--workspace-parent",
        type=Path,
    )

    parser.add_argument(
        "--remote-name",
        default="origin",
    )

    parser.add_argument(
        "--base-branch",
        default="main",
    )

    parser.add_argument(
        "--gh-binary",
        default="gh",
    )

    args = parser.parse_args()

    asyncio.run(
        serve(
            socket_path=args.socket,
            repo_root=args.repo,
            github_repository=args.github_repository,
            repository_url=args.repository_url,
            workspace_parent=args.workspace_parent,
            remote_name=args.remote_name,
            base_branch=args.base_branch,
            gh_binary=args.gh_binary,
        )
    )


if __name__ == "__main__":
    main()
