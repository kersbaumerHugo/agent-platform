from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from agent_platform.domain.coding import CodingTask
from agent_platform.trust.publisher import ChangeSet


class CodingChangeProducer(Protocol):
    """Produce one unverified ChangeSet for a supervised coding task."""

    async def produce(
        self,
        task: CodingTask,
        *,
        execution_id: UUID,
    ) -> ChangeSet: ...


class CodingBaseRevisionMismatchError(RuntimeError):
    def __init__(
        self,
        *,
        expected: str,
        actual: str,
    ) -> None:
        self.expected = expected
        self.actual = actual

        super().__init__(
            f"Coding task base revision mismatch: expected {expected}, produced from {actual}."
        )


@dataclass(frozen=True)
class PreparedCodingTask:
    """Application result ready for a future authoritative verification stage."""

    task_id: UUID
    execution_id: UUID
    change_set: ChangeSet


class SupervisedCodingService:
    """Prepare one coding proposal without verification or publication."""

    def __init__(
        self,
        *,
        producer: CodingChangeProducer,
    ) -> None:
        self._producer = producer

    async def execute(
        self,
        task: CodingTask,
    ) -> PreparedCodingTask:
        execution_id = uuid4()

        change_set = await self._producer.produce(
            task,
            execution_id=execution_id,
        )

        if change_set.base_revision != task.expected_base_revision:
            raise CodingBaseRevisionMismatchError(
                expected=task.expected_base_revision,
                actual=change_set.base_revision,
            )

        return PreparedCodingTask(
            task_id=task.task_id,
            execution_id=execution_id,
            change_set=change_set,
        )
