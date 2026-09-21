from typing import Protocol, TypeVar

from agent_platform.domain.capability import CapabilityDefinition

RequestT = TypeVar("RequestT", contravariant=True)
ResultT = TypeVar("ResultT", covariant=True)


class CapabilityContract(Protocol[RequestT, ResultT]):
    """Typed internal execution boundary for a platform capability."""

    @property
    def definition(self) -> CapabilityDefinition: ...

    async def invoke(
        self,
        request: RequestT,
    ) -> ResultT: ...
