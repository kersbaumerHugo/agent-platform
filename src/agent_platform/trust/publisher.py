from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from agent_platform.trust.change_policy import (
    ChangePolicy,
    ChangePolicyDecision,
)


class FileChangeOperation(StrEnum):
    UPSERT = "upsert"
    DELETE = "delete"


@dataclass(frozen=True)
class FileChange:
    path: str
    operation: FileChangeOperation
    content: str | None = None

    def __post_init__(self) -> None:
        if not self.path.strip():
            raise ValueError("FileChange path must not be empty.")

        if self.operation is FileChangeOperation.UPSERT and self.content is None:
            raise ValueError("UPSERT requires content.")

        if self.operation is FileChangeOperation.DELETE and self.content is not None:
            raise ValueError("DELETE must not include content.")


@dataclass(frozen=True)
class ChangeSet:
    base_revision: str
    branch_name: str
    commit_message: str
    changes: tuple[FileChange, ...]

    def __post_init__(self) -> None:
        if not self.base_revision.strip():
            raise ValueError("base_revision must not be empty.")

        if not self.branch_name.strip():
            raise ValueError("branch_name must not be empty.")

        if not self.commit_message.strip():
            raise ValueError("commit_message must not be empty.")

        if not self.changes:
            raise ValueError("ChangeSet must contain at least one change.")

        paths = [change.path for change in self.changes]

        if len(paths) != len(set(paths)):
            raise ValueError("ChangeSet must not contain duplicate paths.")

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(change.path for change in self.changes)


@dataclass(frozen=True)
class PublicationResult:
    reference: str


class ChangeSink(Protocol):
    async def publish(
        self,
        change_set: ChangeSet,
    ) -> PublicationResult: ...


class ChangeRejectedError(RuntimeError):
    def __init__(
        self,
        decision: ChangePolicyDecision,
    ) -> None:
        self.decision = decision
        super().__init__(
            f"Change rejected: {decision.reason_code}: {', '.join(decision.blocked_paths)}"
        )


class TrustedPublisher:
    def __init__(
        self,
        policy: ChangePolicy,
        sink: ChangeSink,
    ) -> None:
        self._policy = policy
        self._sink = sink

    async def publish(
        self,
        change_set: ChangeSet,
    ) -> PublicationResult:
        decision = self._policy.evaluate(change_set.changed_paths)

        if not decision.allowed:
            raise ChangeRejectedError(decision)

        return await self._sink.publish(change_set)
