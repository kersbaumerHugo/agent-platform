from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from uuid import uuid4

from agent_platform.adapters.runtimes.dsh import DSHRuntime
from agent_platform.contracts.runtime import RuntimeContract
from agent_platform.domain.models import RuntimeRequest
from agent_platform.worker.session import (
    WorkerExecutionRequest,
    WorkerExecutionResult,
)

RuntimeFactory = Callable[[Path], RuntimeContract]


class DshWorkerExecutor:
    """Execute one development task through DSH inside a Worker workspace."""

    def __init__(
        self,
        *,
        dsh_home: Path,
        provider: str,
        model: str,
        profile: str = "sdk",
        request_timeout_seconds: float | None = 120.0,
        patches: tuple[Path, ...] = (),
        env: Mapping[str, str] | None = None,
        runtime_factory: RuntimeFactory | None = None,
    ) -> None:
        if not provider.strip():
            raise ValueError("provider must not be empty.")

        if not model.strip():
            raise ValueError("model must not be empty.")

        self._dsh_home = dsh_home.resolve()
        self._provider = provider
        self._model = model
        self._profile = profile
        self._request_timeout_seconds = request_timeout_seconds
        self._patches = patches
        self._env = dict(env or {})
        self._runtime_factory = runtime_factory

    async def execute(
        self,
        request: WorkerExecutionRequest,
    ) -> WorkerExecutionResult:
        runtime = self._build_runtime(request.workspace)

        prompt = self._build_prompt(request.goal)

        result = await runtime.execute(
            RuntimeRequest(
                run_id=uuid4(),
                agent_id="self-development-worker",
                input=prompt,
            )
        )

        return WorkerExecutionResult(
            summary=result.output,
        )

    def _build_runtime(
        self,
        workspace: Path,
    ) -> RuntimeContract:
        if self._runtime_factory is not None:
            return self._runtime_factory(workspace)

        return DSHRuntime(
            dsh_home=self._dsh_home,
            cwd=workspace,
            provider=self._provider,
            model=self._model,
            profile=self._profile,
            request_timeout_seconds=(self._request_timeout_seconds),
            patches=self._patches,
            env=self._env,
        )

    @staticmethod
    def _build_prompt(
        goal: str,
    ) -> str:
        return (
            "You are the implementation Worker for the Agent Platform.\n\n"
            "Goal:\n"
            f"{goal.strip()}\n\n"
            "Operate only inside the current workspace.\n"
            "Implement the requested change directly in the files.\n"
            "Run relevant local verification when possible.\n"
            "Do not commit, push, create pull requests, or modify "
            "external repository settings.\n"
            "Do not assume your changes are trusted or accepted.\n"
            "When finished, summarize what you changed and what "
            "verification you ran."
        )
