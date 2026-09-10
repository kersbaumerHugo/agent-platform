from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol, cast

from agent_platform.contracts.runtime import RuntimeContract
from agent_platform.domain.models import (
    RuntimeRequest,
    RuntimeResult,
)


class _DSHRunResult(Protocol):
    final_response: str
    finish_reason: str | None


class _DSHClient(Protocol):
    def run(
        self,
        prompt: str,
        *,
        session_id: str,
    ) -> _DSHRunResult: ...

    def close(self) -> None: ...


class DSHRuntime(RuntimeContract):
    def __init__(
        self,
        *,
        dsh_home: Path,
        cwd: Path,
        provider: str,
        model: str,
        profile: str = "sdk",
        request_timeout_seconds: float | None = 120.0,
        patches: tuple[Path, ...] = (),
        env: Mapping[str, str] | None = None,
        client_factory: Callable[[], _DSHClient] | None = None,
    ) -> None:
        if not provider:
            raise ValueError("DSH provider must not be empty.")

        if not model:
            raise ValueError("DSH model must not be empty.")

        self._dsh_home = dsh_home.resolve()
        self._cwd = cwd.resolve()
        self._provider = provider
        self._model = model
        self._profile = profile
        self._request_timeout_seconds = request_timeout_seconds
        self._patches = tuple(patch.resolve() for patch in patches)
        self._env = dict(env or {})
        self._client_factory = client_factory

    @property
    def name(self) -> str:
        return "dsh"

    async def execute(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResult:
        return await asyncio.to_thread(
            self._execute_sync,
            request,
        )

    def _execute_sync(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResult:
        client = self._build_client(request)

        try:
            result = client.run(
                request.input,
                session_id=str(request.run_id),
            )
        finally:
            client.close()

        if not result.final_response.strip():
            raise RuntimeError("DSH completed without a final response.")

        return RuntimeResult(
            output=result.final_response,
        )

    def _build_client(
        self,
        request: RuntimeRequest,
    ) -> _DSHClient:
        if self._client_factory is not None:
            return self._client_factory()

        try:
            from deepseek_harness import DeepSeekHarness
        except ImportError as exc:
            raise RuntimeError(
                'DSH runtime is not installed. Install the optional dependency with ".[dsh]".'
            ) from exc

        runtime_env = dict(self._env)
        runtime_env["AGENT_PLATFORM_RUN_ID"] = str(request.run_id)

        client = DeepSeekHarness(
            dsh_home=str(self._dsh_home),
            cwd=str(self._cwd),
            provider=self._provider,
            model=self._model,
            profile=self._profile,
            patches=tuple(str(patch) for patch in self._patches),
            env=runtime_env,
            request_timeout_seconds=(self._request_timeout_seconds),
        )

        return cast(_DSHClient, client)
