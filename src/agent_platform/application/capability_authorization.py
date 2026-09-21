from collections.abc import Iterable

from agent_platform.domain.authorization import (
    CapabilityAuthorizationDecision,
)
from agent_platform.domain.capability import CapabilityDefinition


class StaticCapabilityAuthorizationPolicy:
    """Fail-closed exact-grant capability authorization policy."""

    version = "m13-v0"

    def __init__(
        self,
        grants: Iterable[tuple[str, str]] = (),
    ) -> None:
        normalized: set[tuple[str, str]] = set()

        for raw_principal_id, raw_capability_name in grants:
            principal_id = raw_principal_id.strip()
            capability_name = raw_capability_name.strip()

            if not principal_id:
                raise ValueError("Authorization grant principal must not be blank.")

            if not capability_name:
                raise ValueError("Authorization grant capability must not be blank.")

            normalized.add(
                (
                    principal_id,
                    capability_name,
                )
            )

        self._grants = frozenset(normalized)

    def authorize(
        self,
        *,
        principal_id: str | None,
        capability: CapabilityDefinition,
    ) -> CapabilityAuthorizationDecision:
        normalized_principal = principal_id.strip() if principal_id is not None else None

        if not normalized_principal:
            return CapabilityAuthorizationDecision(
                policy_version=self.version,
                principal_id=None,
                capability_name=capability.name,
                allowed=False,
                reason_code="missing_principal",
            )

        if (
            normalized_principal,
            capability.name,
        ) not in self._grants:
            return CapabilityAuthorizationDecision(
                policy_version=self.version,
                principal_id=normalized_principal,
                capability_name=capability.name,
                allowed=False,
                reason_code="capability_not_granted",
            )

        return CapabilityAuthorizationDecision(
            policy_version=self.version,
            principal_id=normalized_principal,
            capability_name=capability.name,
            allowed=True,
            reason_code="allowed",
        )
