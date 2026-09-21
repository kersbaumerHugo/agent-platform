from agent_platform.contracts.capability import CapabilityContract
from agent_platform.contracts.repository import (
    RepositoryInspectionBackendContract,
)
from agent_platform.domain.capability import CapabilityDefinition
from agent_platform.domain.repository import (
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
)


class RepositoryInspectionCapability(
    CapabilityContract[
        RepositoryInspectionRequest,
        RepositoryInspectionResult,
    ]
):
    """Expose repository intelligence through a provider-independent capability."""

    def __init__(
        self,
        backend: RepositoryInspectionBackendContract,
    ) -> None:
        self._backend = backend

    @property
    def definition(self) -> CapabilityDefinition:
        return CapabilityDefinition(
            name="repository.inspect",
            description=("Inspect repository targets and return structured repository evidence."),
        )

    async def invoke(
        self,
        request: RepositoryInspectionRequest,
    ) -> RepositoryInspectionResult:
        return await self._backend.inspect(request)
