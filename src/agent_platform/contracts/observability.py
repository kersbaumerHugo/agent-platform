from typing import Protocol

from agent_platform.domain.observability import ObservationEvent


class ObservationContract(Protocol):
    def record(self, event: ObservationEvent) -> None: ...
