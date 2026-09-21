from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from agent_platform.trust.publisher import ChangeSet
from agent_platform.worker.change_set import ChangeSetBuilder
from agent_platform.worker.workspace import DisposableWorkerWorkspace


@dataclass(frozen=True)
class WorkerDevelopmentTask:
    goal: str
    branch_name: str
    commit_message: str
    execution_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.goal.strip():
            raise ValueError("goal must not be empty.")

        if not self.branch_name.strip():
            raise ValueError("branch_name must not be empty.")

        if not self.commit_message.strip():
            raise ValueError("commit_message must not be empty.")


@dataclass(frozen=True)
class WorkerExecutionRequest:
    goal: str
    workspace: Path
    execution_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True)
class WorkerExecutionResult:
    summary: str


class WorkerExecutor(Protocol):
    async def execute(
        self,
        request: WorkerExecutionRequest,
    ) -> WorkerExecutionResult: ...


class WorkerDevelopmentSession:
    def __init__(
        self,
        *,
        workspace: DisposableWorkerWorkspace,
        executor: WorkerExecutor,
    ) -> None:
        self._workspace = workspace
        self._executor = executor

    async def run(
        self,
        task: WorkerDevelopmentTask,
    ) -> ChangeSet:
        with self._workspace.open() as workspace:
            await self._executor.execute(
                WorkerExecutionRequest(
                    goal=task.goal,
                    workspace=workspace.path,
                    execution_id=task.execution_id,
                )
            )

            change_set = ChangeSetBuilder(workspace.path).build(
                branch_name=task.branch_name,
                commit_message=task.commit_message,
            )

            if change_set.base_revision != workspace.base_revision:
                raise RuntimeError("ChangeSet base revision differs from Worker workspace base.")

            return change_set
