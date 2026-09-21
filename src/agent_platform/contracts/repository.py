from typing import Protocol

from agent_platform.domain.repository import (
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
)


class RepositoryInspectionBackendContract(Protocol):
    """Provider contract for repository intelligence."""

    async def inspect(
        self,
        request: RepositoryInspectionRequest,
    ) -> RepositoryInspectionResult: ...
