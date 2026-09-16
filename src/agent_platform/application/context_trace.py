from collections import defaultdict
from collections.abc import Sequence

from agent_platform.domain.context_budget import BudgetedContextBundle
from agent_platform.domain.context_preparation import RecallPlan
from agent_platform.domain.context_rendering import RenderedContext
from agent_platform.domain.context_trace import (
    ContextBudgetTrace,
    ContextInjectionTrace,
    ContextPreparationTrace,
    ContextProviderResult,
    ContextProviderTrace,
    ContextRenderingTrace,
)


class ContextTraceBuilder:
    @property
    def version(self) -> str:
        return "v0"

    def build(
        self,
        *,
        plan: RecallPlan,
        provider_results: Sequence[ContextProviderResult],
        assembler_version: str,
        budget_policy_version: str,
        token_estimator_version: str,
        budgeted: BudgetedContextBundle,
        rendered: RenderedContext,
        injector_name: str,
        injector_version: str,
    ) -> ContextPreparationTrace:
        request_by_id = {request.request_id: request for request in plan.requests}
        grouped: dict[str, list[ContextProviderResult]] = defaultdict(list)
        seen_provider_keys: set[tuple[str, str]] = set()

        for result in provider_results:
            request_id = result.trace.request_id
            request = request_by_id.get(request_id)
            if request is None:
                raise ValueError(
                    "ContextTraceBuilder received a provider result for an unknown request_id."
                )

            if result.trace.context != request.context:
                raise ValueError(
                    "ContextTraceBuilder provider trace context must match RecallPlan."
                )

            provider_key = (request_id, result.trace.provider)
            if provider_key in seen_provider_keys:
                raise ValueError(
                    "ContextTraceBuilder received duplicate provider results "
                    "for the same request_id and provider."
                )

            seen_provider_keys.add(provider_key)
            grouped[request_id].append(result)

        provider_traces: list[ContextProviderTrace] = []
        for request in plan.requests:
            results = grouped.get(request.request_id, [])
            if not results:
                raise ValueError(
                    "ContextTraceBuilder requires at least one provider result "
                    "for every RecallPlan request."
                )

            provider_traces.extend(
                result.trace
                for result in sorted(
                    results,
                    key=lambda value: value.trace.provider,
                )
            )

        return ContextPreparationTrace(
            version=self.version,
            planner=plan.planner,
            planner_version=plan.version,
            provider_traces=tuple(provider_traces),
            assembler_version=assembler_version,
            budget=ContextBudgetTrace(
                policy_version=budget_policy_version,
                estimator_version=token_estimator_version,
                budget_tokens=budgeted.budget_tokens,
                estimated_tokens=budgeted.estimated_tokens,
                dropped_item_ids=budgeted.dropped_item_ids,
            ),
            rendering=ContextRenderingTrace(
                renderer=rendered.renderer,
                version=rendered.version,
                content_hash=rendered.content_hash,
            ),
            injection=ContextInjectionTrace(
                injector=injector_name,
                version=injector_version,
            ),
        )
