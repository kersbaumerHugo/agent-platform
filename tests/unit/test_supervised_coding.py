from __future__ import annotations

from uuid import UUID

import pytest

from agent_platform.adapters.workers.supervised_coding import (
    WorkerCodingChangeProducer,
)
from agent_platform.application.supervised_coding import (
    CodingBaseRevisionMismatchError,
    SupervisedCodingService,
)
from agent_platform.domain.coding import CodingTask
from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
)
from agent_platform.worker.session import WorkerDevelopmentTask

TASK_ID = UUID("12000000-0000-4000-8000-000000000002")
EXECUTION_ID = UUID("12000000-0000-4000-8000-000000000007")
BASE_REVISION = "9b278bea9a88085454f60a97e10c76495da0d7b1"
OTHER_REVISION = "a" * 40


def make_task() -> CodingTask:
    return CodingTask(
        task_id=TASK_ID,
        goal="Add a deterministic supervised coding test.",
        expected_base_revision=BASE_REVISION,
    )


def make_change_set(
    *,
    base_revision: str = BASE_REVISION,
) -> ChangeSet:
    return ChangeSet(
        base_revision=base_revision,
        branch_name=f"coding/{TASK_ID}",
        commit_message=f"chore: apply supervised coding task {TASK_ID}",
        changes=(
            FileChange(
                path="tests/unit/test_example.py",
                operation=FileChangeOperation.UPSERT,
                content="def test_example() -> None:\n    assert True\n",
            ),
        ),
    )


class RecordingProducer:
    def __init__(
        self,
        change_set: ChangeSet,
    ) -> None:
        self.change_set = change_set
        self.tasks: list[CodingTask] = []
        self.execution_ids: list[UUID] = []

    async def produce(
        self,
        task: CodingTask,
        *,
        execution_id: UUID,
    ) -> ChangeSet:
        self.tasks.append(task)
        self.execution_ids.append(execution_id)
        return self.change_set


class RecordingWorkerSession:
    def __init__(
        self,
        change_set: ChangeSet,
    ) -> None:
        self.change_set = change_set
        self.tasks: list[WorkerDevelopmentTask] = []

    async def run(
        self,
        task: WorkerDevelopmentTask,
    ) -> ChangeSet:
        self.tasks.append(task)
        return self.change_set


@pytest.mark.asyncio
async def test_supervised_coding_service_produces_unverified_change_set() -> None:
    task = make_task()
    change_set = make_change_set()
    producer = RecordingProducer(change_set)
    service = SupervisedCodingService(producer=producer)

    result = await service.execute(task)

    assert result.task_id == TASK_ID
    assert result.change_set == change_set
    assert producer.tasks == [task]
    assert producer.execution_ids == [result.execution_id]


@pytest.mark.asyncio
async def test_supervised_coding_service_preserves_task_identity() -> None:
    task = make_task()
    producer = RecordingProducer(make_change_set())
    service = SupervisedCodingService(producer=producer)

    result = await service.execute(task)

    assert result.task_id == task.task_id


@pytest.mark.asyncio
async def test_supervised_coding_service_fails_closed_on_base_revision_mismatch() -> None:
    task = make_task()
    producer = RecordingProducer(
        make_change_set(
            base_revision=OTHER_REVISION,
        )
    )
    service = SupervisedCodingService(producer=producer)

    with pytest.raises(
        CodingBaseRevisionMismatchError,
        match="base revision mismatch",
    ) as exc_info:
        await service.execute(task)

    assert exc_info.value.expected == BASE_REVISION
    assert exc_info.value.actual == OTHER_REVISION


@pytest.mark.asyncio
async def test_worker_adapter_maps_canonical_task_to_worker_task() -> None:
    task = make_task()
    change_set = make_change_set()
    session = RecordingWorkerSession(change_set)
    producer = WorkerCodingChangeProducer(session=session)

    result = await producer.produce(
        task,
        execution_id=EXECUTION_ID,
    )

    assert result is change_set
    assert session.tasks == [
        WorkerDevelopmentTask(
            execution_id=EXECUTION_ID,
            goal=task.goal,
            branch_name=f"coding/{TASK_ID}",
            commit_message=f"chore: apply supervised coding task {TASK_ID}",
        )
    ]


def test_worker_adapter_derives_publication_metadata_deterministically() -> None:
    assert WorkerCodingChangeProducer.branch_name(TASK_ID) == (
        "coding/12000000-0000-4000-8000-000000000002"
    )
    assert WorkerCodingChangeProducer.commit_message(TASK_ID) == (
        "chore: apply supervised coding task 12000000-0000-4000-8000-000000000002"
    )


@pytest.mark.asyncio
async def test_application_path_has_no_publisher_dependency() -> None:
    task = make_task()
    producer = RecordingProducer(make_change_set())
    service = SupervisedCodingService(producer=producer)

    result = await service.execute(task)

    assert result.change_set.changed_paths == ("tests/unit/test_example.py",)
