from __future__ import annotations

import argparse
import asyncio
import os
import sys
from functools import partial
from pathlib import Path

from agent_platform.adapters.workers.dsh import DshWorkerExecutor
from agent_platform.worker.dsh_lifecycle import lifecycle_observer
from agent_platform.worker.execution_budget import (
    ModelCallBudgetExceededError,
    PhaseAwareModelCallBudget,
)
from agent_platform.worker.self_verification import (
    build_self_repair_goal,
    run_worker_self_verification,
)
from agent_platform.worker.session import (
    WorkerExecutionRequest,
    WorkerExecutionResult,
    WorkerExecutor,
)
from agent_platform.worker.workspace_hygiene import apply_workspace_hygiene

_GATEWAY_HOST = "127.0.0.1"
_GATEWAY_PORT = 18080
_DSH_HOME = Path("/tmp/agent-platform-dsh")
_DSH_CONTEXT_PATCH = _DSH_HOME / "context-policy.patch.yml"

_COMPACTION_THRESHOLD_RATIO = 0.55
_COMPACTION_RETAIN_TOKENS = 1024
_COMPACTION_MAX_TOKENS = 768
_COMPACTION_RETRIES = 1
_MAX_OVERFLOW_RETRIES = 1
_TOOL_RESULT_PRUNER_THRESHOLD_CHARS = 8192
_TOOL_RESULT_PRUNER_HEAD_CHARS = 4096
_TOOL_RESULT_PRUNER_TAIL_CHARS = 1024
_MAX_MODEL_CALLS_PER_EXECUTION = 32
_INITIAL_MODEL_CALLS_MAX = 24


def _context_policy_patch(
    *,
    context_window: int,
    max_output_tokens: int,
) -> str:
    return (
        "- id: llm-deepseek\n"
        "  config:\n"
        "    apiKeyEnv: DEEPSEEK_API_KEY\n"
        f"    defaultContextWindow: {context_window}\n"
        f"    maxTokens: {max_output_tokens}\n"
        "    streamIdleTimeoutMs: 172800000\n"
        "\n"
        "- insert:\n"
        "    - id: token-meter\n"
        "      name: '@deepseek-ai/dsh-token-meter'\n"
        "\n"
        "    - id: tool-result-pruner\n"
        "      name: '@deepseek-ai/dsh-compaction-tool-result-pruner'\n"
        "      config:\n"
        f"        thresholdChars: {_TOOL_RESULT_PRUNER_THRESHOLD_CHARS}\n"
        f"        headChars: {_TOOL_RESULT_PRUNER_HEAD_CHARS}\n"
        f"        tailChars: {_TOOL_RESULT_PRUNER_TAIL_CHARS}\n"
        "\n"
        "    - id: compaction-basic\n"
        "      name: '@deepseek-ai/dsh-compaction-basic'\n"
        "      config:\n"
        f"        thresholdRatio: {_COMPACTION_THRESHOLD_RATIO}\n"
        f"        retainTokens: {_COMPACTION_RETAIN_TOKENS}\n"
        f"        maxTokens: {_COMPACTION_MAX_TOKENS}\n"
        f"        compactionRetries: {_COMPACTION_RETRIES}\n"
        f"        maxOverflowRetries: {_MAX_OVERFLOW_RETRIES}\n"
        "        auto: true\n"
    )


def _content_length(headers: bytes) -> int:
    decoded = headers.decode("iso-8859-1")
    lines = decoded.split("\r\n")

    for line in lines[1:]:
        name, separator, value = line.partition(":")

        if separator and name.strip().lower() == "content-length":
            length = int(value.strip())

            if length < 0:
                raise ValueError("Negative content length.")

            return length

    raise ValueError("Content-Length is required.")


async def _proxy_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    socket_path: Path,
    budget: PhaseAwareModelCallBudget,
    budget_exhausted: asyncio.Event,
) -> None:
    upstream_writer: asyncio.StreamWriter | None = None

    try:
        headers = await reader.readuntil(b"\r\n\r\n")

        if len(headers) > 64 * 1024:
            raise ValueError("Gateway request headers are too large.")

        body_length = _content_length(headers)

        if body_length > 8 * 1024 * 1024:
            raise ValueError("Gateway request body is too large.")

        body = await reader.readexactly(body_length)

        try:
            budget.consume()
        except ModelCallBudgetExceededError:
            budget_exhausted.set()
            return

        upstream_reader, upstream_writer = await asyncio.open_unix_connection(
            socket_path,
        )

        upstream_writer.write(headers)
        upstream_writer.write(body)
        await upstream_writer.drain()

        while True:
            chunk = await upstream_reader.read(64 * 1024)

            if not chunk:
                break

            writer.write(chunk)
            await writer.drain()

    finally:
        if upstream_writer is not None:
            upstream_writer.close()

            try:
                await upstream_writer.wait_closed()
            except (ConnectionError, OSError):
                pass

        writer.close()

        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass


async def _watch_budget_exhaustion(server: asyncio.Server, budget_exhausted: asyncio.Event) -> None:
    await budget_exhausted.wait()
    server.close()
    await server.wait_closed()


class WorkerPhaseBudgetReachedError(RuntimeError):
    """Raised when one Worker model-call phase reaches its allowance."""


class _PhaseBoundWorkerExecutor:
    def __init__(
        self,
        *,
        executor: WorkerExecutor,
        gateway_socket: Path,
        total_max_calls: int,
        initial_max_calls: int,
    ) -> None:
        self._executor = executor
        self._gateway_socket = gateway_socket
        self._budget = PhaseAwareModelCallBudget(
            max_calls=total_max_calls,
        )
        self._initial_max_calls = initial_max_calls
        self._attempts = 0

    @property
    def consumed_calls(self) -> int:
        return self._budget.consumed_calls

    @property
    def remaining_calls(self) -> int:
        return self._budget.remaining_calls

    async def execute(
        self,
        request: WorkerExecutionRequest,
    ) -> WorkerExecutionResult:
        if self._budget.remaining_calls <= 0:
            raise WorkerPhaseBudgetReachedError("No model calls remain for another Worker phase.")

        if self._attempts == 0:
            requested_limit = self._initial_max_calls
        else:
            requested_limit = self._budget.remaining_calls

        phase_limit = min(
            requested_limit,
            self._budget.remaining_calls,
        )

        self._attempts += 1
        self._budget.begin_phase(phase_limit)

        limit_reached = asyncio.Event()

        server = await asyncio.start_server(
            partial(
                _proxy_request,
                socket_path=self._gateway_socket,
                budget=self._budget,
                budget_exhausted=limit_reached,
            ),
            host=_GATEWAY_HOST,
            port=_GATEWAY_PORT,
        )

        watcher_task = asyncio.create_task(
            _watch_budget_exhaustion(
                server,
                limit_reached,
            )
        )

        try:
            try:
                result = await self._executor.execute(request)
            except Exception:
                if limit_reached.is_set():
                    raise WorkerPhaseBudgetReachedError(
                        "Worker model-call phase limit reached."
                    ) from None

                raise

            if limit_reached.is_set():
                raise WorkerPhaseBudgetReachedError("Worker model-call phase limit reached.")

            return result

        finally:
            server.close()
            await server.wait_closed()

            if not watcher_task.done():
                watcher_task.cancel()

            try:
                await watcher_task
            except asyncio.CancelledError:
                pass


async def _execute_with_bounded_self_repair(
    *,
    executor: WorkerExecutor,
    goal: str,
    workspace: Path,
) -> WorkerExecutionResult:
    initial_phase_limited = False

    try:
        result = await executor.execute(
            WorkerExecutionRequest(
                goal=goal,
                workspace=workspace,
            )
        )
    except WorkerPhaseBudgetReachedError:
        initial_phase_limited = True
        result = None

    await apply_workspace_hygiene(workspace)

    verification = await run_worker_self_verification(
        workspace,
    )

    if verification.passed and not initial_phase_limited:
        assert result is not None
        return result

    try:
        repaired = await executor.execute(
            WorkerExecutionRequest(
                goal=build_self_repair_goal(
                    original_goal=goal,
                    verification=verification,
                    phase_limited=initial_phase_limited,
                ),
                workspace=workspace,
            )
        )
    except WorkerPhaseBudgetReachedError:
        repaired = None

    await apply_workspace_hygiene(workspace)

    final_verification = await run_worker_self_verification(
        workspace,
    )

    if final_verification.passed:
        if repaired is not None:
            return repaired

        return WorkerExecutionResult(
            summary=(
                "Worker repair phase reached its model-call limit, but "
                "deterministic self-verification passes. The candidate "
                "still requires authoritative trusted verification."
            )
        )

    if repaired is None:
        summary = "Worker repair phase reached its model-call limit."
    else:
        summary = repaired.summary.rstrip()

    return WorkerExecutionResult(
        summary=(
            f"{summary}\\n\\n"
            "Deterministic Worker self-verification remains failing after "
            "the single bounded self-repair attempt. The candidate must "
            "still pass authoritative trusted verification."
        )
    )


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()

    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")

    return value


async def _run(args: argparse.Namespace) -> int:
    goal = sys.stdin.read()

    if not goal.strip():
        raise RuntimeError("Sandbox coding process received an empty goal.")

    gateway_socket = Path(_required_env("AGENT_PLATFORM_GATEWAY_SOCKET"))

    _DSH_HOME.mkdir(
        parents=True,
        exist_ok=True,
    )

    _DSH_CONTEXT_PATCH.write_text(
        _context_policy_patch(
            context_window=args.context_window,
            max_output_tokens=args.max_output_tokens,
        ),
        encoding="utf-8",
    )

    runtime_env = {
        "DEEPSEEK_BASE_URL": _required_env("DEEPSEEK_BASE_URL"),
        "DEEPSEEK_API_KEY": _required_env("DEEPSEEK_API_KEY"),
        "HOME": _required_env("HOME"),
        "TMPDIR": _required_env("TMPDIR"),
        "XDG_CACHE_HOME": _required_env("XDG_CACHE_HOME"),
        "DSH_CONTEXT_WINDOW": str(args.context_window),
    }

    executor = DshWorkerExecutor(
        dsh_home=_DSH_HOME,
        provider=args.provider,
        model=args.model,
        profile=args.profile,
        request_timeout_seconds=(args.request_timeout_seconds),
        patches=(_DSH_CONTEXT_PATCH,),
        env=runtime_env,
        notification_callback=lifecycle_observer(),
    )

    phase_executor = _PhaseBoundWorkerExecutor(
        executor=executor,
        gateway_socket=gateway_socket,
        total_max_calls=_MAX_MODEL_CALLS_PER_EXECUTION,
        initial_max_calls=_INITIAL_MODEL_CALLS_MAX,
    )

    try:
        result = await _execute_with_bounded_self_repair(
            executor=phase_executor,
            goal=goal,
            workspace=Path.cwd(),
        )
    finally:
        await executor.close()

    sys.stdout.write(result.summary)

    if result.summary and not result.summary.endswith("\n"):
        sys.stdout.write("\n")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one coding Worker inside the trusted sandbox."
    )

    parser.add_argument(
        "--provider",
        required=True,
    )
    parser.add_argument(
        "--model",
        required=True,
    )
    parser.add_argument(
        "--profile",
        default="sdk-minimal",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=180.0,
    )
    parser.add_argument(
        "--context-window",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--max-output-tokens",
        required=True,
        type=int,
    )

    args = parser.parse_args()

    if args.request_timeout_seconds <= 0:
        parser.error("--request-timeout-seconds must be greater than zero")

    if args.context_window <= 0:
        parser.error("--context-window must be greater than zero")

    if args.max_output_tokens <= 0:
        parser.error("--max-output-tokens must be greater than zero")

    if args.max_output_tokens >= args.context_window:
        parser.error("--max-output-tokens must be smaller than --context-window")

    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
