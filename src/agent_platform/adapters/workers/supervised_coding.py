from __future__ import annotations

from typing import Protocol
from uuid import UUID

from agent_platform.domain.coding import CodingTask
from agent_platform.trust.publisher import ChangeSet
from agent_platform.worker.session import WorkerDevelopmentTask


class WorkerCodingSession(Protocol):
    async def run(
        self,
        task: WorkerDevelopmentTask,
    ) -> ChangeSet: ...


class WorkerCodingChangeProducer:
    """Map a platform CodingTask onto the current Worker development session."""

    def __init__(
        self,
        *,
        session: WorkerCodingSession,
    ) -> None:
        self._session = session

    async def produce(
        self,
        task: CodingTask,
        *,
        execution_id: UUID,
    ) -> ChangeSet:
        return await self._session.run(
            WorkerDevelopmentTask(
                execution_id=execution_id,
                goal=task.goal,
                branch_name=self.branch_name(task.task_id),
                commit_message=self.commit_message(task.task_id),
            )
        )

    @staticmethod
    def branch_name(task_id: UUID) -> str:
        return f"coding/{task_id}"

    @staticmethod
    def commit_message(task_id: UUID) -> str:
        return f"chore: apply supervised coding task {task_id}"
