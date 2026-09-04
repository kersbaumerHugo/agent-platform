from typing import Protocol

from agent_platform.domain.model import ModelRequest, ModelResult


class ModelContract(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def generate(self, request: ModelRequest) -> ModelResult: ...
