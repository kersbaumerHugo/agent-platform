from typing import Protocol

from agent_platform.domain.evaluation import EvaluationCase, EvaluationResult


class EvaluationContract(Protocol):
    @property
    def name(self) -> str: ...

    async def evaluate(
        self,
        case: EvaluationCase,
    ) -> EvaluationResult: ...
