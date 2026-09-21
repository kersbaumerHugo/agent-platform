from agent_platform.contracts.repository import (
    RepositoryInspectionBackendContract,
)
from agent_platform.contracts.repowise import (
    RepoWiseClientContract,
)
from agent_platform.domain.repository import (
    RepositoryEvidence,
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
)


class RepoWiseRepositoryBackend(RepositoryInspectionBackendContract):
    """Adapt normalized RepoWise context into platform repository evidence."""

    def __init__(
        self,
        client: RepoWiseClientContract,
    ) -> None:
        self._client = client

    async def inspect(
        self,
        request: RepositoryInspectionRequest,
    ) -> RepositoryInspectionResult:
        snapshot = await self._client.get_context(
            request.targets,
        )

        evidence = tuple(
            RepositoryEvidence(
                target=item.target,
                summary=item.summary,
                source_reference=(f"repowise:get_context:{item.target}"),
            )
            for item in snapshot.items
        )

        return RepositoryInspectionResult(
            evidence=evidence,
            indexed_revision=snapshot.indexed_commit,
            stale=snapshot.stale_warning is not None,
        )
