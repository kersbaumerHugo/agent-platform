from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from agent_platform.trust.publisher import ChangeSet
from agent_platform.worker.change_set import (
    ChangeSetBuilder,
    WorkspaceContainsNoChangesError,
)
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


class WorkerNoChangesError(RuntimeError):
    def __init__(
        self,
        *,
        first_summary: str,
        retry_summary: str,
    ) -> None:
        self.first_summary = first_summary
        self.retry_summary = retry_summary

        super().__init__(
            "Worker completed two attempts without workspace changes. "
            f"First summary: {first_summary!r}. "
            f"Retry summary: {retry_summary!r}."
        )


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
            first_result = await self._executor.execute(
                WorkerExecutionRequest(
                    goal=task.goal,
                    workspace=workspace.path,
                    execution_id=task.execution_id,
                )
            )

            builder = ChangeSetBuilder(workspace.path)

            try:
                change_set = builder.build(
                    branch_name=task.branch_name,
                    commit_message=task.commit_message,
                )
            except WorkspaceContainsNoChangesError:
                retry_result = await self._executor.execute(
                    WorkerExecutionRequest(
                        goal=self._build_retry_goal(task.goal),
                        workspace=workspace.path,
                        execution_id=uuid4(),
                    )
                )

                try:
                    change_set = builder.build(
                        branch_name=task.branch_name,
                        commit_message=task.commit_message,
                    )
                except WorkspaceContainsNoChangesError as exc:
                    raise WorkerNoChangesError(
                        first_summary=first_result.summary,
                        retry_summary=retry_result.summary,
                    ) from exc

            if change_set.base_revision != workspace.base_revision:
                raise RuntimeError("ChangeSet base revision differs from Worker workspace base.")

            return change_set

    @staticmethod
    def _build_retry_goal(
        goal: str,
    ) -> str:
        return (
            f"{goal.strip()}\n\n"
            "The previous Worker attempt completed without modifying the "
            "workspace. This is the final bounded implementation retry. "
            "Use the available shell or tools to make the requested changes "
            "before responding. Do not return only analysis, a plan, intent, "
            "or narration. Before finishing, run `git status --short` and "
            "ensure that it reports at least one requested workspace change."
        )
