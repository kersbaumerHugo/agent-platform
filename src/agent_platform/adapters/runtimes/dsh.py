from agent_platform.contracts.runtime import RuntimeContract
from agent_platform.domain.models import RuntimeRequest, RuntimeResult


class DSHRuntime(RuntimeContract):
    # Primeiro adapter real.
    # Mantido como placeholder até o core + smoke test ficarem estáveis,
    # porque o DSH ainda está em developer preview.

    @property
    def name(self) -> str:
        return "dsh"

    async def execute(self, request: RuntimeRequest) -> RuntimeResult:
        raise NotImplementedError("Implement DSH adapter after the core smoke test is green.")
