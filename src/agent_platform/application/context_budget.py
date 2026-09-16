from agent_platform.contracts.context import TokenEstimatorContract
from agent_platform.domain.context import ContextBundle, ContextSection
from agent_platform.domain.context_budget import (
    BudgetedContextBundle,
    ContextBudget,
)


class Utf8ByteTokenEstimator:
    def __init__(
        self,
        *,
        bytes_per_token: int = 4,
    ) -> None:
        if bytes_per_token <= 0:
            raise ValueError("bytes_per_token must be greater than 0.")

        self._bytes_per_token = bytes_per_token

    @property
    def version(self) -> str:
        return "utf8-bytes-v0"

    def estimate(
        self,
        text: str,
    ) -> int:
        byte_count = len(text.encode("utf-8"))
        if byte_count == 0:
            return 0

        return (byte_count + self._bytes_per_token - 1) // self._bytes_per_token


class DeterministicContextBudgetPolicy:
    def __init__(
        self,
        *,
        estimator: TokenEstimatorContract,
    ) -> None:
        self._estimator = estimator

    @property
    def version(self) -> str:
        return "canonical-prefix-v0"

    def apply(
        self,
        bundle: ContextBundle,
        budget: ContextBudget,
    ) -> BudgetedContextBundle:
        budget_tokens = budget.available_context_tokens
        estimated_tokens = 0
        exhausted = False
        dropped_item_ids: list[str] = []
        retained_sections: list[ContextSection] = []

        for section in bundle.sections:
            retained_items = []

            for item in section.items:
                if exhausted:
                    dropped_item_ids.append(item.item_id)
                    continue

                item_tokens = self._estimator.estimate(item.content)

                if item_tokens < 0:
                    raise ValueError("TokenEstimatorContract returned a negative estimate.")

                if estimated_tokens + item_tokens <= budget_tokens:
                    retained_items.append(item)
                    estimated_tokens += item_tokens
                    continue

                exhausted = True
                dropped_item_ids.append(item.item_id)

            if retained_items:
                retained_sections.append(
                    ContextSection(
                        context=section.context,
                        items=tuple(retained_items),
                    )
                )

        return BudgetedContextBundle(
            bundle=ContextBundle(
                sections=tuple(retained_sections),
            ),
            budget_tokens=budget_tokens,
            estimated_tokens=estimated_tokens,
            dropped_item_ids=tuple(dropped_item_ids),
        )
