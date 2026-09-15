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

    @property
    def name(self) -> str:
        return "fake"

    async def execute(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResult:
        self.requests.append(request)

        return RuntimeResult(output="Implemented and verified.")


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
