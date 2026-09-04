from typing import Protocol

from agent_platform.domain.models import RuntimeRequest, RuntimeResult


class RuntimeContract(Protocol):
    @property
    def name(self) -> str: ...

    async def execute(self, request: RuntimeRequest) -> RuntimeResult: ...
