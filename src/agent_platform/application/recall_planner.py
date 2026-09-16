from agent_platform.domain.context_preparation import (
    RecallIntent,
    RecallPlan,
    RecallRequest,
)


class DeterministicRecallPlanner:
    def __init__(self, *, limit_per_context: int = 5) -> None:
        if limit_per_context <= 0:
            raise ValueError("limit_per_context must be greater than 0.")

        self._limit_per_context = limit_per_context

    @property
    def name(self) -> str:
        return "deterministic"

    @property
    def version(self) -> str:
        return "v0"

    async def plan(
        self,
        intent: RecallIntent,
    ) -> RecallPlan:
        query = f"{intent.objective}\n{intent.step_input}"

        requests = tuple(
            RecallRequest(
                request_id=(f"{index:03d}:{context.role.value}:{context.namespace}"),
                context=context,
                query=query,
                limit=self._limit_per_context,
            )
            for index, context in enumerate(intent.contexts)
        )

        return RecallPlan(
            planner=self.name,
            version=self.version,
            requests=requests,
        )
