from collections.abc import Sequence
from typing import Protocol

from agent_platform.domain.context import ContextBundle, ContextContribution
from agent_platform.domain.context_budget import (
    BudgetedContextBundle,
    ContextBudget,
)
from agent_platform.domain.context_preparation import (
    RecallIntent,
    RecallPlan,
    RecallRequest,
)
from agent_platform.domain.context_rendering import RenderedContext


class RecallPlannerContract(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    async def plan(
        self,
        intent: RecallIntent,
    ) -> RecallPlan: ...


class ContextProviderContract(Protocol):
    @property
    def name(self) -> str: ...

    async def provide(
        self,
        request: RecallRequest,
    ) -> ContextContribution: ...


class ContextAssemblerContract(Protocol):
    @property
    def version(self) -> str: ...

    def assemble(
        self,
        contributions: Sequence[ContextContribution],
    ) -> ContextBundle: ...


class TokenEstimatorContract(Protocol):
    @property
    def version(self) -> str: ...

    def estimate(
        self,
        text: str,
    ) -> int: ...


class ContextBudgetPolicyContract(Protocol):
    @property
    def version(self) -> str: ...

    def apply(
        self,
        bundle: ContextBundle,
        budget: ContextBudget,
    ) -> BudgetedContextBundle: ...


class ContextRendererContract(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def render(
        self,
        budgeted: BudgetedContextBundle,
    ) -> RenderedContext: ...
