from dataclasses import dataclass, field

import pytest

from agent_platform.adapters.capabilities.repository import (
    RepositoryInspectionCapability,
)
from agent_platform.contracts.capability import CapabilityContract
from agent_platform.domain.repository import (
    RepositoryEvidence,
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
)


@dataclass
class RecordingRepositoryBackend:
    requests: list[RepositoryInspectionRequest] = field(default_factory=list)

    async def inspect(
        self,
        request: RepositoryInspectionRequest,
    ) -> RepositoryInspectionResult:
        self.requests.append(request)

        return RepositoryInspectionResult(
            evidence=(
                RepositoryEvidence(
                    target=request.targets[0],
                    summary="Repository evidence.",
                    source_reference="repository:index",
                ),
            ),
            indexed_revision="a" * 40,
            stale=False,
        )


@pytest.mark.asyncio
async def test_repository_inspection_capability_is_typed() -> None:
    backend = RecordingRepositoryBackend()

    capability: CapabilityContract[
        RepositoryInspectionRequest,
        RepositoryInspectionResult,
    ] = RepositoryInspectionCapability(backend)

    request = RepositoryInspectionRequest(
        targets=("src/agent_platform/domain/tool.py",),
    )

    result = await capability.invoke(request)

    assert capability.definition.name == "repository.inspect"
    assert backend.requests == [request]
    assert result.evidence[0].target == request.targets[0]


@pytest.mark.asyncio
async def test_repository_inspection_preserves_backend_freshness() -> None:
    backend = RecordingRepositoryBackend()
    capability = RepositoryInspectionCapability(backend)

    result = await capability.invoke(
        RepositoryInspectionRequest(
            targets=("src/agent_platform",),
        )
    )

    assert result.indexed_revision == "a" * 40
    assert result.stale is False
