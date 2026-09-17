from collections.abc import Sequence

from agent_platform.application.context_trace import ContextTraceBuilder
from agent_platform.contracts.context import (
    ContextAssemblerContract,
    ContextBudgetPolicyContract,
    ContextInjectorContract,
    ContextProviderContract,
    ContextRendererContract,
    RecallPlannerContract,
    TokenEstimatorContract,
)
from agent_platform.domain.context import ContextRef
from agent_platform.domain.context_budget import ContextBudget
from agent_platform.domain.context_preparation import (
    ContextPreparationResult,
    RecallIntent,
)


class PrepareContext:
    def __init__(
        self,
        *,
        planner: RecallPlannerContract,
        provider: ContextProviderContract,
        assembler: ContextAssemblerContract,
        budget_policy: ContextBudgetPolicyContract,
        token_estimator: TokenEstimatorContract,
        renderer: ContextRendererContract,
        injector: ContextInjectorContract,
        trace_builder: ContextTraceBuilder,
    ) -> None:
        self._planner = planner
        self._provider = provider
        self._assembler = assembler
        self._budget_policy = budget_policy
        self._token_estimator = token_estimator
        self._renderer = renderer
        self._injector = injector
        self._trace_builder = trace_builder

    async def execute(
        self,
        *,
        objective: str,
        step_input: str,
        contexts: Sequence[ContextRef],
        budget: ContextBudget,
    ) -> ContextPreparationResult:
        intent = RecallIntent(
            objective=objective,
            step_input=step_input,
            contexts=tuple(contexts),
        )
        plan = await self._planner.plan(intent)

        provider_results = [await self._provider.provide(request) for request in plan.requests]

        bundle = self._assembler.assemble(tuple(result.contribution for result in provider_results))
        budgeted = self._budget_policy.apply(
            bundle,
            budget,
        )
        rendered = self._renderer.render(budgeted)

        trace = self._trace_builder.build(
            plan=plan,
            provider_results=provider_results,
            assembler_version=self._assembler.version,
            budget_policy_version=self._budget_policy.version,
            token_estimator_version=self._token_estimator.version,
            budgeted=budgeted,
            rendered=rendered,
            injector_name=self._injector.name,
            injector_version=self._injector.version,
        )

        return ContextPreparationResult(
            rendered=rendered,
            trace=trace,
        )
