from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRoute:
    route: str
    model: str


class ModelRoutingPolicy:
    """Map semantic decision routes to concrete model identifiers."""

    def __init__(
        self,
        *,
        routes: tuple[ModelRoute, ...],
    ) -> None:
        if not routes:
            raise ValueError("At least one model route is required.")

        mapping = {route.route: route.model for route in routes}

        if len(mapping) != len(routes):
            raise ValueError("Model route names must be unique.")

        self._mapping = mapping

    def resolve(self, route: str) -> str:
        try:
            return self._mapping[route]
        except KeyError as exc:
            raise ValueError(f"No model configured for route {route!r}.") from exc
