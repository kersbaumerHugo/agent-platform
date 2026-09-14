from dataclasses import dataclass, field

import pytest

from agent_platform.adapters.github.proposal import (
    PullRequestChangeSink,
    PullRequestResult,
    PullRequestSpec,
)
from agent_platform.trust.change_policy import ChangePolicy
from agent_platform.trust.publisher import (
    ChangeRejectedError,
    ChangeSet,
    FileChange,
    FileChangeOperation,
    PublicationResult,
    TrustedPublisher,
)


@dataclass
class FakeGitSink:
    published: list[ChangeSet] = field(default_factory=list)

    async def publish(
        self,
        change_set: ChangeSet,
    ) -> PublicationResult:
        self.published.append(change_set)

        return PublicationResult(reference=(f"git-remote:origin/{change_set.branch_name}@deadbeef"))


@dataclass
class FakePullRequestClient:
    created: list[PullRequestSpec] = field(default_factory=list)

    async def create_pull_request(
        self,
        spec: PullRequestSpec,
    ) -> PullRequestResult:
        self.created.append(spec)

        return PullRequestResult(reference="github:pr/42")


def make_change_set(
    path: str = "src/agent_platform/example.py",
) -> ChangeSet:
    return ChangeSet(
        base_revision="abc123",
        branch_name="agent/example",
        commit_message="feat: example",
        changes=(
            FileChange(
                path=path,
                operation=FileChangeOperation.UPSERT,
                content="VALUE = 42\n",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_allowed_change_creates_pull_request() -> None:
    git_sink = FakeGitSink()
    pr_client = FakePullRequestClient()

    sink = PullRequestChangeSink(
        git_sink=git_sink,
        pr_client=pr_client,
    )

    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=sink,
    )

    change_set = make_change_set()

    result = await publisher.publish(change_set)

    assert result.reference == "github:pr/42"
    assert git_sink.published == [change_set]

    assert len(pr_client.created) == 1

    spec = pr_client.created[0]

    assert spec.head_branch == "agent/example"
    assert spec.base_branch == "main"
    assert spec.title == "feat: example"

    assert "src/agent_platform/example.py" in spec.body
    assert "requires trusted CI gates" in spec.body


@pytest.mark.asyncio
async def test_protected_change_creates_neither_branch_nor_pr() -> None:
    git_sink = FakeGitSink()
    pr_client = FakePullRequestClient()

    sink = PullRequestChangeSink(
        git_sink=git_sink,
        pr_client=pr_client,
    )

    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=sink,
    )

    change_set = make_change_set(".github/workflows/ci.yml")

    with pytest.raises(ChangeRejectedError):
        await publisher.publish(change_set)

    assert git_sink.published == []
    assert pr_client.created == []


@pytest.mark.asyncio
async def test_github_adapter_itself_is_protected() -> None:
    git_sink = FakeGitSink()
    pr_client = FakePullRequestClient()

    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=PullRequestChangeSink(
            git_sink=git_sink,
            pr_client=pr_client,
        ),
    )

    change_set = make_change_set("src/agent_platform/adapters/github/proposal.py")

    with pytest.raises(ChangeRejectedError):
        await publisher.publish(change_set)

    assert git_sink.published == []
    assert pr_client.created == []


@pytest.mark.asyncio
async def test_pull_request_targets_configured_base_branch() -> None:
    git_sink = FakeGitSink()
    pr_client = FakePullRequestClient()

    publisher = TrustedPublisher(
        policy=ChangePolicy(),
        sink=PullRequestChangeSink(
            git_sink=git_sink,
            pr_client=pr_client,
            base_branch="release",
        ),
    )

    await publisher.publish(make_change_set())

    assert pr_client.created[0].base_branch == "release"
