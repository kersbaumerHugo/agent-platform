from agent_platform.contracts.model import ModelContract
from agent_platform.domain.model import ModelRequest, ModelResult


class ModelGateway:
    def __init__(self, model: ModelContract) -> None:
        self._model = model

    async def generate(self, request: ModelRequest) -> ModelResult:
        return await self._model.generate(request)
