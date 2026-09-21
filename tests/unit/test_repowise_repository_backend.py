from dataclasses import dataclass, field

import pytest

from agent_platform.adapters.repository.repowise import (
    RepoWiseRepositoryBackend,
)
from agent_platform.contracts.repowise import (
    RepoWiseContextItem,
    RepoWiseContextSnapshot,
)
from agent_platform.domain.repository import (
    RepositoryInspectionRequest,
)


@dataclass
class RecordingRepoWiseClient:
    snapshot: RepoWiseContextSnapshot
    requests: list[tuple[str, ...]] = field(default_factory=list)

    async def get_context(
        self,
        targets: tuple[str, ...],
    ) -> RepoWiseContextSnapshot:
        self.requests.append(targets)
        return self.snapshot


@pytest.mark.asyncio
async def test_repowise_backend_maps_context_to_repository_evidence() -> None:
    client = RecordingRepoWiseClient(
        snapshot=RepoWiseContextSnapshot(
            items=(
                RepoWiseContextItem(
                    target="src/agent_platform/domain/tool.py",
                    summary="Defines tool boundary contracts.",
                ),
            ),
            indexed_commit="abcdef123456",
        )
    )

    backend = RepoWiseRepositoryBackend(client)

    request = RepositoryInspectionRequest(
        targets=("src/agent_platform/domain/tool.py",),
    )

    result = await backend.inspect(request)

    assert client.requests == [request.targets]

    assert len(result.evidence) == 1
    assert result.evidence[0].target == request.targets[0]
    assert result.evidence[0].source_reference == (
        "repowise:get_context:src/agent_platform/domain/tool.py"
    )

    assert result.indexed_revision == "abcdef123456"
    assert result.stale is False


@pytest.mark.asyncio
async def test_repowise_backend_preserves_stale_signal() -> None:
    client = RecordingRepoWiseClient(
        snapshot=RepoWiseContextSnapshot(
            items=(
                RepoWiseContextItem(
                    target="src/agent_platform",
                    summary="Platform package.",
                ),
            ),
            indexed_commit="abcdef123456",
            stale=True,
        )
    )

    backend = RepoWiseRepositoryBackend(client)

    result = await backend.inspect(
        RepositoryInspectionRequest(
            targets=("src/agent_platform",),
        )
    )

    assert result.stale is True
