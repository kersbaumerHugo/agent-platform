from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from uuid import uuid4

from agent_platform.adapters.runtimes.dsh import (
    DSHNotificationCallback,
    DSHRuntime,
)
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
        notification_callback: DSHNotificationCallback | None = None,
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
        self._notification_callback = notification_callback
        self._runtime: RuntimeContract | None = None
        self._runtime_workspace: Path | None = None

    async def execute(
        self,
        request: WorkerExecutionRequest,
    ) -> WorkerExecutionResult:
        workspace = request.workspace.resolve()
        runtime = self._runtime

        if runtime is None:
            runtime = self._build_runtime(workspace)
            self._runtime = runtime
            self._runtime_workspace = workspace
        elif workspace != self._runtime_workspace:
            raise RuntimeError(
                "DshWorkerExecutor cannot change workspace while its runtime is open."
            )

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

    async def close(self) -> None:
        runtime = self._runtime

        self._runtime = None
        self._runtime_workspace = None

        if runtime is None:
            return

        close = getattr(runtime, "close", None)

        if close is not None:
            await asyncio.to_thread(close)

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
            notification_callback=(self._notification_callback),
        )

    @staticmethod
    def _build_prompt(
        goal: str,
    ) -> str:
        return (
            "You are the implementation Worker for the Agent Platform.\n\n"
            "Goal:\n"
            f"{goal.strip()}\n\n"
            "Operate only inside the current workspace.\n\n"
            "Use this execution protocol:\n\n"
            "1. INSPECT ENOUGH TO ACT\n"
            "- Inspect the exact target file first.\n"
            "- Then inspect only the minimum directly relevant production "
            "contracts, types, and existing tests required to make a correct "
            "first edit.\n"
            "- Stop broad repository exploration once enough evidence exists "
            "to make the first safe workspace change.\n\n"
            "2. PLAN ENOUGH TO EDIT SAFELY\n"
            "- Form a concise working plan containing: target files, confirmed "
            "contracts/types to reuse, expected behavioral sequence, explicit "
            "acceptance criteria, and verification commands.\n"
            "- Check the plan against every explicit constraint in the goal.\n"
            "- Planning is bounded preparation for action, not a separate task.\n"
            "- If the goal requires code changes, make the first workspace edit "
            "before continuing optional exploration.\n"
            "- Prefer inspect -> edit -> inspect a missing detail -> edit over "
            "inspect everything -> plan everything -> edit at the end.\n\n"
            "3. IMPLEMENT FROM EVIDENCE\n"
            "- Implement the requested change directly in the files.\n"
            "- Reuse repository APIs and contracts confirmed during inspection. "
            "Do not invent APIs, fields, attributes, enum values, or behavior "
            "that you have not confirmed in the repository.\n"
            "- Treat exact counts, sequences, file scopes, types, enum values, "
            "and assertions specified by the goal as hard contracts.\n"
            "- A plan is useful only if it leads to workspace changes when the "
            "goal requires workspace changes.\n\n"
            "4. VERIFY AND REFINE\n"
            "- Run relevant local verification when possible.\n"
            "- Compare the implementation and verification results against every "
            "acceptance criterion from the goal before finishing.\n"
            "- If verification exposes a mismatch, inspect only the missing "
            "detail, repair the implementation, and verify again when the "
            "remaining execution budget allows.\n\n"
            "Do not commit, push, create pull requests, or modify "
            "external repository settings.\n"
            "Do not assume your changes are trusted or accepted.\n"
            "When finished, summarize what you changed and what "
            "verification you ran."
        )
