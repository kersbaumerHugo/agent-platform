from typing import Protocol

from agent_platform.contracts.capability import CapabilityContract
from agent_platform.domain.capability import CapabilityDefinition
from agent_platform.domain.coding import CodingResult, CodingTask


class CodingExecutionService(Protocol):
    async def execute(
        self,
        task: CodingTask,
    ) -> CodingResult: ...


class SupervisedCodingCapability(CapabilityContract[CodingTask, CodingResult]):
    """Expose trusted supervised coding as one typed platform capability."""

    def __init__(
        self,
        service: CodingExecutionService,
    ) -> None:
        self._service = service

    @property
    def definition(self) -> CapabilityDefinition:
        return CapabilityDefinition(
            name="coding.execute",
            description=(
                "Execute one supervised coding task through trusted verification and publication."
            ),
        )

    async def invoke(
        self,
        request: CodingTask,
    ) -> CodingResult:
        return await self._service.execute(request)
