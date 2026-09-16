from collections import defaultdict
from collections.abc import Sequence

from agent_platform.domain.context import (
    ContextBundle,
    ContextContribution,
    ContextItem,
    ContextRole,
    ContextSection,
)

_ROLE_ORDER = {
    ContextRole.SHARED: 0,
    ContextRole.DELIVERY: 1,
    ContextRole.SUBJECT: 2,
}


class DeterministicContextAssembler:
    @property
    def version(self) -> str:
        return "v0"

    def assemble(
        self,
        contributions: Sequence[ContextContribution],
    ) -> ContextBundle:
        grouped: dict[
            tuple[ContextRole, str],
            list[ContextContribution],
        ] = defaultdict(list)

        for contribution in contributions:
            if contribution.items:
                key = (
                    contribution.context.role,
                    contribution.context.namespace,
                )
                grouped[key].append(contribution)

        sections: list[ContextSection] = []

        for key in sorted(
            grouped,
            key=lambda value: (
                _ROLE_ORDER[value[0]],
                value[1],
            ),
        ):
            group = sorted(
                grouped[key],
                key=self._contribution_sort_key,
            )
            context = group[0].context
            items = self._merge_items(group)

            if items:
                sections.append(
                    ContextSection(
                        context=context,
                        items=items,
                    )
                )

        return ContextBundle(
            sections=tuple(sections),
        )

    @staticmethod
    def _contribution_sort_key(
        contribution: ContextContribution,
    ) -> tuple[str, tuple[str, ...]]:
        return (
            contribution.provider,
            tuple(item.item_id for item in contribution.items),
        )

    @staticmethod
    def _merge_items(
        contributions: Sequence[ContextContribution],
    ) -> tuple[ContextItem, ...]:
        items: list[ContextItem] = []
        seen: dict[str, ContextItem] = {}

        for contribution in contributions:
            for item in contribution.items:
                existing = seen.get(item.item_id)

                if existing is None:
                    seen[item.item_id] = item
                    items.append(item)
                    continue

                if existing != item:
                    raise ValueError(
                        f"ContextAssembler received conflicting items for item_id {item.item_id!r}."
                    )

        return tuple(items)
