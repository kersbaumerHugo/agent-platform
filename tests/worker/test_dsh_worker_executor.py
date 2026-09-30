from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agent_platform.adapters.workers.dsh import (
    DshWorkerExecutor,
)
from agent_platform.domain.models import (
    RuntimeRequest,
    RuntimeResult,
)
from agent_platform.worker.session import (
    WorkerExecutionRequest,
)


@dataclass
class FakeRuntime:
    requests: list[RuntimeRequest] = field(default_factory=list)
    closed: bool = False

    @property
    def name(self) -> str:
        return "fake"

    async def execute(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResult:
        self.requests.append(request)

        return RuntimeResult(output="Implemented and verified.")

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_dsh_worker_maps_workspace_and_goal(
    tmp_path: Path,
) -> None:
    runtime = FakeRuntime()
    seen_workspaces: list[Path] = []

    def runtime_factory(
        workspace: Path,
    ) -> FakeRuntime:
        seen_workspaces.append(workspace)
        return runtime

    executor = DshWorkerExecutor(
        dsh_home=tmp_path / "dsh",
        provider="test-provider",
        model="test-model",
        runtime_factory=runtime_factory,
    )

    result = await executor.execute(
        WorkerExecutionRequest(
            goal="Add a health endpoint.",
            workspace=tmp_path,
        )
    )

    assert seen_workspaces == [tmp_path]

    assert len(runtime.requests) == 1

    request = runtime.requests[0]

    assert request.agent_id == "self-development-worker"

    assert "Add a health endpoint." in request.input

    assert "Do not commit, push, create pull requests" in request.input

    assert "Operate only inside the current workspace" in request.input

    assert result.summary == ("Implemented and verified.")


def test_rejects_empty_provider(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="provider must not be empty",
    ):
        DshWorkerExecutor(
            dsh_home=tmp_path / "dsh",
            provider="",
            model="test-model",
        )


def test_rejects_empty_model(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="model must not be empty",
    ):
        DshWorkerExecutor(
            dsh_home=tmp_path / "dsh",
            provider="test-provider",
            model="",
        )


@pytest.mark.asyncio
async def test_dsh_worker_reuses_runtime_for_same_workspace(
    tmp_path: Path,
) -> None:
    runtime = FakeRuntime()
    factory_calls = 0

    def runtime_factory(
        workspace: Path,
    ) -> FakeRuntime:
        nonlocal factory_calls
        factory_calls += 1

        assert workspace == tmp_path.resolve()

        return runtime

    executor = DshWorkerExecutor(
        dsh_home=tmp_path / "dsh",
        provider="test-provider",
        model="test-model",
        runtime_factory=runtime_factory,
    )

    await executor.execute(
        WorkerExecutionRequest(
            goal="Initial implementation.",
            workspace=tmp_path,
        )
    )

    await executor.execute(
        WorkerExecutionRequest(
            goal="Repair implementation.",
            workspace=tmp_path,
        )
    )

    assert factory_calls == 1
    assert len(runtime.requests) == 2
    assert runtime.closed is False

    await executor.close()

    assert runtime.closed is True


@pytest.mark.asyncio
async def test_dsh_worker_rejects_workspace_change_while_runtime_open(
    tmp_path: Path,
) -> None:
    first_workspace = tmp_path / "first"
    second_workspace = tmp_path / "second"

    first_workspace.mkdir()
    second_workspace.mkdir()

    runtime = FakeRuntime()

    executor = DshWorkerExecutor(
        dsh_home=tmp_path / "dsh",
        provider="test-provider",
        model="test-model",
        runtime_factory=lambda workspace: runtime,
    )

    await executor.execute(
        WorkerExecutionRequest(
            goal="Initial implementation.",
            workspace=first_workspace,
        )
    )

    with pytest.raises(
        RuntimeError,
        match="cannot change workspace",
    ):
        await executor.execute(
            WorkerExecutionRequest(
                goal="Different task.",
                workspace=second_workspace,
            )
        )

    await executor.close()


def test_dsh_worker_prompt_requires_plan_before_editing() -> None:
    prompt = DshWorkerExecutor._build_prompt(
        "Modify exactly one test file and add exactly two assertions."
    )

    inspect = prompt.index("1. INSPECT BEFORE EDITING")
    plan = prompt.index("2. PLAN BEFORE EDITING")
    implement = prompt.index("3. IMPLEMENT FROM EVIDENCE")
    verify = prompt.index("4. VERIFY AGAINST THE PLAN")

    assert inspect < plan < implement < verify

    assert "before modifying anything" in prompt
    assert "target files" in prompt
    assert "existing contracts/types to reuse" in prompt
    assert "explicit acceptance criteria" in prompt
    assert "verification commands" in prompt

    assert "Planning is not completion" in prompt
    assert "do not stop after producing the plan" in prompt

    assert "Do not invent APIs, fields, attributes, enum values, or behavior" in prompt

    assert (
        "Treat exact counts, sequences, file scopes, types, enum values, "
        "and assertions specified by the goal as hard contracts." in prompt
    )

    assert "against every acceptance criterion" in prompt

    assert "Modify exactly one test file and add exactly two assertions." in prompt
