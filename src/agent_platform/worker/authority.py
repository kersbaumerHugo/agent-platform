from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CodingAuthority(StrEnum):
    """Authorities intentionally granted to model-controlled coding execution."""

    WORKSPACE_READ = "workspace.read"
    WORKSPACE_WRITE = "workspace.write"
    PROCESS_EXECUTION = "process.execute"
    MODEL_GATEWAY_REQUEST = "model_gateway.request"


class ForbiddenCodingAuthority(StrEnum):
    """Authorities that remain outside the M12 supervised coding sandbox."""

    HOST_FILESYSTEM = "host.filesystem"
    PUBLISHER_SOCKET = "publisher.socket"
    DOCKER_SOCKET = "docker.socket"
    DIRECT_LAN = "network.lan"
    INTERNET_EGRESS = "network.internet"
    PUBLICATION_CREDENTIAL = "publication.credential"
    GIT_PUSH = "git.push"
    MERGE = "git.merge"
    PRIVILEGE_ESCALATION = "process.privilege_escalation"


@dataclass(frozen=True, init=False)
class CodingAuthorityPolicy:
    """Fixed M12 V0 authority envelope owned by the trusted controller."""

    version: str = "m12-v0"

    allowed: tuple[CodingAuthority, ...] = (
        CodingAuthority.WORKSPACE_READ,
        CodingAuthority.WORKSPACE_WRITE,
        CodingAuthority.PROCESS_EXECUTION,
        CodingAuthority.MODEL_GATEWAY_REQUEST,
    )

    denied: tuple[ForbiddenCodingAuthority, ...] = (
        ForbiddenCodingAuthority.HOST_FILESYSTEM,
        ForbiddenCodingAuthority.PUBLISHER_SOCKET,
        ForbiddenCodingAuthority.DOCKER_SOCKET,
        ForbiddenCodingAuthority.DIRECT_LAN,
        ForbiddenCodingAuthority.INTERNET_EGRESS,
        ForbiddenCodingAuthority.PUBLICATION_CREDENTIAL,
        ForbiddenCodingAuthority.GIT_PUSH,
        ForbiddenCodingAuthority.MERGE,
        ForbiddenCodingAuthority.PRIVILEGE_ESCALATION,
    )

    def allows(
        self,
        capability: CodingAuthority,
    ) -> bool:
        return capability in self.allowed

    def denies(
        self,
        authority: ForbiddenCodingAuthority,
    ) -> bool:
        return authority in self.denied
