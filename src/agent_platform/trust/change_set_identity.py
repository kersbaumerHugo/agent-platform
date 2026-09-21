from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from agent_platform.trust.change_request import serialize_change_set
from agent_platform.trust.publisher import ChangeSet

_CHANGE_SET_IDENTITY_VERSION = "v1"
_CHANGE_SET_IDENTITY_DOMAIN = b"agent-platform.change-set.v1\x00"
_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ChangeSetIdentity:
    """Stable identity for the semantic publication payload of one ChangeSet."""

    version: str
    sha256: str

    def __post_init__(self) -> None:
        if self.version != _CHANGE_SET_IDENTITY_VERSION:
            raise ValueError("Unsupported ChangeSet identity version.")

        if not _SHA256_HEX_PATTERN.fullmatch(self.sha256):
            raise ValueError("ChangeSet sha256 must be 64 lowercase hexadecimal characters.")

    @property
    def reference(self) -> str:
        return f"{self.version}:sha256:{self.sha256}"


def identify_change_set(change_set: ChangeSet) -> ChangeSetIdentity:
    """Return a deterministic identity for the exact semantic ChangeSet."""

    canonical = ChangeSet(
        base_revision=change_set.base_revision,
        branch_name=change_set.branch_name,
        commit_message=change_set.commit_message,
        changes=tuple(
            sorted(
                change_set.changes,
                key=lambda change: change.path,
            )
        ),
    )
    serialized = serialize_change_set(canonical).encode("utf-8")
    digest = hashlib.sha256(
        _CHANGE_SET_IDENTITY_DOMAIN + serialized,
    ).hexdigest()

    return ChangeSetIdentity(
        version=_CHANGE_SET_IDENTITY_VERSION,
        sha256=digest,
    )
