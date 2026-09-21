from typing import Protocol

from agent_platform.domain.authorization import (
    CapabilityAuthorizationDecision,
)
from agent_platform.domain.capability import CapabilityDefinition


class CapabilityAuthorizationContract(Protocol):
    """Decide whether one principal may invoke one platform capability."""

    def authorize(
        self,
        *,
        principal_id: str | None,
        capability: CapabilityDefinition,
    ) -> CapabilityAuthorizationDecision: ...
