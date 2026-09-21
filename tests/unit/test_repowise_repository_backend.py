from dataclasses import dataclass, field

import pytest

from agent_platform.adapters.repository.repowise import (
    RepoWiseRepositoryBackend,
)
from agent_platform.contracts.repowise import (
    RepoWiseContextItem,
    RepoWiseContextSnapshot,
    RepoWiseSymbol,
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
                    target=("src/agent_platform/domain/tool.py"),
                    summary=("Defines tool boundary contracts."),
                    symbols=(
                        RepoWiseSymbol(
                            name="ToolDefinition",
                            kind="class",
                            signature="class ToolDefinition",
                            line=7,
                        ),
                    ),
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

    evidence = result.evidence[0]

    assert evidence.target == request.targets[0]
    assert evidence.source_reference == ("repowise:get_context:src/agent_platform/domain/tool.py")

    assert len(evidence.symbols) == 1

    symbol = evidence.symbols[0]

    assert symbol.name == "ToolDefinition"
    assert symbol.kind == "class"
    assert symbol.signature == "class ToolDefinition"
    assert symbol.line == 7

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
