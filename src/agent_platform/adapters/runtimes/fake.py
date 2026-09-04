from agent_platform.contracts.runtime import RuntimeContract
from agent_platform.domain.models import RuntimeRequest, RuntimeResult


class FakeRuntime(RuntimeContract):
    @property
    def name(self) -> str:
        return "fake"

    async def execute(self, request: RuntimeRequest) -> RuntimeResult:
        return RuntimeResult(
            output=f"[fake-runtime] agent={request.agent_id} input={request.input}"
        )
