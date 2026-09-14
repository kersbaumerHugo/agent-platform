from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_platform.trust.publisher import (
    ChangeSet,
    ChangeSink,
    PublicationResult,
)


@dataclass(frozen=True)
class PullRequestSpec:
    head_branch: str
    base_branch: str
    title: str
    body: str


@dataclass(frozen=True)
class PullRequestResult:
    reference: str


class PullRequestClient(Protocol):
    async def create_pull_request(
        self,
        spec: PullRequestSpec,
    ) -> PullRequestResult: ...


class PullRequestChangeSink:
    """Publish a Git branch, then open a pull request for that branch."""

    def __init__(
        self,
        git_sink: ChangeSink,
        pr_client: PullRequestClient,
        *,
        base_branch: str = "main",
    ) -> None:
        self._git_sink = git_sink
        self._pr_client = pr_client
        self._base_branch = base_branch

    async def publish(
        self,
        change_set: ChangeSet,
    ) -> PublicationResult:
        git_result = await self._git_sink.publish(change_set)

        pr_result = await self._pr_client.create_pull_request(
            PullRequestSpec(
                head_branch=change_set.branch_name,
                base_branch=self._base_branch,
                title=change_set.commit_message,
                body=self._build_body(
                    change_set=change_set,
                    git_reference=git_result.reference,
                ),
            )
        )

        return PublicationResult(
            reference=pr_result.reference,
        )

    @staticmethod
    def _build_body(
        *,
        change_set: ChangeSet,
        git_reference: str,
    ) -> str:
        changed_paths = "\n".join(f"- `{path}`" for path in change_set.changed_paths)

        return (
            "Automated Agent Platform change proposal.\n\n"
            "## Change\n\n"
            f"{change_set.commit_message}\n\n"
            "## Changed paths\n\n"
            f"{changed_paths}\n\n"
            "## Publication\n\n"
            f"`{git_reference}`\n\n"
            "This proposal requires trusted CI gates and human approval."
        )
