from collections.abc import Iterable

from agent_platform.contracts.observability import ObservationContract
from agent_platform.domain.observability import ObservationEvent


class CompositeObserver:
    def __init__(
        self,
        observers: Iterable[ObservationContract],
    ) -> None:
        self._observers = tuple(observers)

    def record(self, event: ObservationEvent) -> None:
        for observer in self._observers:
            observer.record(event)
