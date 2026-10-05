from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from agent_platform.trust.goal_acceptance import GoalAcceptanceEvaluator
from agent_platform.trust.publisher import ChangeSet
from agent_platform.trust.workspace_change_evidence import (
    TrustedWorkspaceChangeCollector,
    WorkspaceChangeEvidence,
)
from agent_platform.worker.change_set import (
    ChangeSetBuilder,
    WorkspaceContainsNoChangesError,
)
from agent_platform.worker.workspace import DisposableWorkerWorkspace, WorkerWorkspace


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


class WorkerChangeSetEvidenceMismatchError(RuntimeError):
    def __init__(
        self,
        *,
        trusted_paths: tuple[str, ...],
        built_paths: tuple[str, ...],
    ) -> None:
        self.trusted_paths = trusted_paths
        self.built_paths = built_paths

        super().__init__(
            "ChangeSet paths do not match trusted workspace change evidence: "
            f"trusted={trusted_paths!r}, built={built_paths!r}."
        )


class WorkerDevelopmentSession:
    def __init__(
        self,
        *,
        workspace: DisposableWorkerWorkspace,
        executor: WorkerExecutor,
        trusted_repo_root: Path | None = None,
    ) -> None:
        self._workspace = workspace
        self._executor = executor
        self._change_collector = (
            TrustedWorkspaceChangeCollector(
                trusted_repo_root=trusted_repo_root,
            )
            if trusted_repo_root is not None
            else None
        )
        self._goal_acceptance = GoalAcceptanceEvaluator()

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
            evidence = self._collect_trusted_evidence(
                workspace=workspace,
            )

            if evidence is None:
                # Legacy Worker path: preserve the previous bounded
                # no-change retry behavior when no trusted collector
                # is configured.
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

            else:
                # Trusted supervised-coding path: use revision-bound
                # evidence to decide whether a real change exists.
                acceptance = self._goal_acceptance.evaluate(
                    changed_paths=evidence.changed_paths,
                )

                if not acceptance.accepted:
                    retry_result = await self._executor.execute(
                        WorkerExecutionRequest(
                            goal=self._build_retry_goal(task.goal),
                            workspace=workspace.path,
                            execution_id=uuid4(),
                        )
                    )

                    evidence = self._collect_trusted_evidence(
                        workspace=workspace,
                    )

                    if evidence is None:
                        raise RuntimeError(
                            "Trusted workspace evidence collector disappeared "
                            "during Worker execution."
                        )

                    acceptance = self._goal_acceptance.evaluate(
                        changed_paths=evidence.changed_paths,
                    )

                    if not acceptance.accepted:
                        raise WorkerNoChangesError(
                            first_summary=first_result.summary,
                            retry_summary=retry_result.summary,
                        )

                try:
                    change_set = builder.build(
                        branch_name=task.branch_name,
                        commit_message=task.commit_message,
                    )
                except WorkspaceContainsNoChangesError as exc:
                    raise WorkerChangeSetEvidenceMismatchError(
                        trusted_paths=evidence.changed_paths,
                        built_paths=(),
                    ) from exc

                if change_set.changed_paths != evidence.changed_paths:
                    raise WorkerChangeSetEvidenceMismatchError(
                        trusted_paths=evidence.changed_paths,
                        built_paths=change_set.changed_paths,
                    )

            if change_set.base_revision != workspace.base_revision:
                raise RuntimeError("ChangeSet base revision differs from Worker workspace base.")

            return change_set

    def _collect_trusted_evidence(
        self,
        *,
        workspace: WorkerWorkspace,
    ) -> WorkspaceChangeEvidence | None:
        collector = self._change_collector

        if collector is None:
            return None

        evidence = collector.collect(
            workspace=workspace.path,
            base_revision=workspace.base_revision,
        )

        if evidence.base_revision != workspace.base_revision:
            raise RuntimeError(
                "Trusted workspace evidence base revision does not match Worker workspace base."
            )

        return evidence

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
