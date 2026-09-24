from __future__ import annotations

import shlex
from typing import Protocol
from uuid import UUID, uuid4

from agent_platform.domain.coding import CodingTask
from agent_platform.trust.publisher import ChangeSet
from agent_platform.trust.verification import (
    VerificationOutcome,
    VerificationResult,
)
from agent_platform.trust.verification_binding import ChangeSetMaterializer
from agent_platform.trust.verification_profile import AuthoritativeVerificationProfile
from agent_platform.worker.change_set import ChangeSetBuilder
from agent_platform.worker.session import (
    WorkerDevelopmentTask,
    WorkerExecutionRequest,
    WorkerExecutor,
)


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


class WorkerCodingRepairProducer:
    """Repair one failed candidate inside a disposable materialized workspace."""

    def __init__(
        self,
        *,
        materializer: ChangeSetMaterializer,
        executor: WorkerExecutor,
    ) -> None:
        self._materializer = materializer
        self._executor = executor

    async def repair(
        self,
        *,
        task: CodingTask,
        candidate: ChangeSet,
        verification: VerificationResult,
        attempt: int,
    ) -> ChangeSet:
        with self._materializer.materialize(candidate) as materialized:
            await self._executor.execute(
                WorkerExecutionRequest(
                    goal=self._build_repair_goal(
                        task=task,
                        verification=verification,
                        attempt=attempt,
                    ),
                    workspace=materialized.workspace,
                    execution_id=uuid4(),
                )
            )

            repaired = ChangeSetBuilder(materialized.workspace).build(
                branch_name=candidate.branch_name,
                commit_message=candidate.commit_message,
            )

        if repaired.base_revision != candidate.base_revision:
            raise RuntimeError(
                "Repaired ChangeSet base revision differs from the failed candidate."
            )

        return repaired

    @staticmethod
    def _build_repair_goal(
        *,
        task: CodingTask,
        verification: VerificationResult,
        attempt: int,
    ) -> str:
        failed_steps = tuple(
            step for step in verification.steps if step.outcome is not VerificationOutcome.PASS
        )

        if not failed_steps:
            raise ValueError("Rejected verification must contain at least one non-passing step.")

        profile = AuthoritativeVerificationProfile()
        commands = {step.check: shlex.join(step.argv) for step in profile.steps}

        feedback: list[str] = []

        for step in failed_steps:
            try:
                command = commands[step.check]
            except KeyError as exc:
                raise ValueError(
                    f"No authoritative command is known for check: {step.check.value}"
                ) from exc

            exit_code = str(step.exit_code) if step.exit_code is not None else "none"

            feedback.append(f"- {step.check.value}: exit_code={exit_code}; command={command}")

        rendered_feedback = "\n".join(feedback)

        return (
            f"{task.goal.strip()}\n\n"
            f"Authoritative verification rejected the current candidate. "
            f"This is bounded repair attempt {attempt}. The failed candidate "
            "is already materialized in the workspace. Repair the existing "
            "implementation; do not discard requested valid changes.\n\n"
            "Non-passing authoritative checks:\n"
            f"{rendered_feedback}\n\n"
            "Run the listed failing authoritative commands after repairing. "
            "You may run broader checks if useful. Do not commit, push, open "
            "a pull request, or change platform-owned publication metadata. "
            "Before finishing, run `git status --short` and ensure the repair "
            "actually changed the candidate."
        )
