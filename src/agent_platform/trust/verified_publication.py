from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_platform.trust.change_set_identity import (
    ChangeSetIdentity,
    identify_change_set,
)
from agent_platform.trust.publisher import (
    ChangeSet,
    PublicationResult,
)
from agent_platform.trust.verification_binding import VerifiedChangeSet


class ChangeSetPublicationAuthority(Protocol):
    async def publish(
        self,
        change_set: ChangeSet,
    ) -> PublicationResult: ...


class VerifiedPublicationIdentityMismatchError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedPublicationResult:
    reference: str
    identity: ChangeSetIdentity

    def __post_init__(self) -> None:
        if not self.reference.strip():
            raise ValueError("Verified publication reference must not be empty.")


class VerifiedChangePublisher:
    """Publish only a ChangeSet already bound to passing authoritative evidence."""

    def __init__(
        self,
        *,
        publisher: ChangeSetPublicationAuthority,
    ) -> None:
        self._publisher = publisher

    async def publish(
        self,
        verified: VerifiedChangeSet,
    ) -> VerifiedPublicationResult:
        current_identity = identify_change_set(verified.change_set)

        if current_identity != verified.identity:
            raise VerifiedPublicationIdentityMismatchError(
                "Verified ChangeSet identity changed before publication."
            )

        result = await self._publisher.publish(verified.change_set)

        return VerifiedPublicationResult(
            reference=result.reference,
            identity=verified.identity,
        )
