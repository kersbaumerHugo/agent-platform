from threading import RLock
from uuid import UUID

from agent_platform.domain.context_preparation import (
    ContextPreparationResult,
)


class InMemoryRunContextBindings:
    """Process-local, ephemeral prepared-context bindings keyed by run_id."""

    def __init__(self) -> None:
        self._bindings: dict[UUID, ContextPreparationResult] = {}
        self._required: set[UUID] = set()
        self._lock = RLock()

    def require(
        self,
        run_id: UUID,
    ) -> None:
        with self._lock:
            self._required.add(run_id)

    def is_required(
        self,
        run_id: UUID,
    ) -> bool:
        with self._lock:
            return run_id in self._required

    def bind(
        self,
        run_id: UUID,
        prepared: ContextPreparationResult,
    ) -> None:
        with self._lock:
            existing = self._bindings.get(run_id)

            if existing is None:
                self._bindings[run_id] = prepared
                return

            if existing != prepared:
                raise ValueError(
                    "Run context binding already exists with different prepared context."
                )

    def resolve(
        self,
        run_id: UUID,
    ) -> ContextPreparationResult | None:
        with self._lock:
            return self._bindings.get(run_id)

    def release(
        self,
        run_id: UUID,
    ) -> None:
        with self._lock:
            self._bindings.pop(run_id, None)
            self._required.discard(run_id)


default_run_context_bindings = InMemoryRunContextBindings()
