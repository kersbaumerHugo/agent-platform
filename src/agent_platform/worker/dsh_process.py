from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from time import monotonic

from agent_platform.adapters.workers.dsh import (
    DshWorkerExecutor,
)
from agent_platform.worker.session import (
    WorkerExecutionRequest,
)


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()

    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")

    return value


def _lifecycle_observer() -> Callable[[object], None]:
    started_at = monotonic()

    def observe(notification: object) -> None:
        method = getattr(
            notification,
            "method",
            None,
        )

        payload = getattr(
            notification,
            "payload",
            None,
        )

        if not isinstance(method, str):
            return

        if not isinstance(payload, dict):
            return

        record: dict[str, object] = {
            "elapsed_seconds": round(
                monotonic() - started_at,
                3,
            ),
            "method": method,
        }

        if method == "session.status":
            status = payload.get("status")

            if isinstance(status, str):
                record["status"] = status

        if method == "session.event":
            event = payload.get("event")

            if isinstance(event, dict):
                event_type = event.get("type")

                if isinstance(event_type, str):
                    record["event_type"] = event_type

        print(
            "DSH_LIFECYCLE "
            + json.dumps(
                record,
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )

    return observe


def _optional_timeout() -> float | None:
    raw = os.environ.get("AGENT_PLATFORM_DSH_REQUEST_TIMEOUT_SECONDS")

    if raw is None or not raw.strip():
        return 120.0

    if raw.strip().lower() == "none":
        return None

    value = float(raw)

    if value <= 0:
        raise ValueError("AGENT_PLATFORM_DSH_REQUEST_TIMEOUT_SECONDS must be greater than zero.")

    return value


async def _run() -> int:
    goal = sys.stdin.read()

    if not goal.strip():
        raise RuntimeError("Worker process received an empty goal.")

    runtime_env: dict[str, str] = {}

    for name in (
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_API_KEY",
    ):
        value = os.environ.get(name)

        if value:
            runtime_env[name] = value

    executor = DshWorkerExecutor(
        dsh_home=Path(_required_env("AGENT_PLATFORM_DSH_HOME")),
        provider=_required_env("AGENT_PLATFORM_DSH_PROVIDER"),
        model=_required_env("AGENT_PLATFORM_DSH_MODEL"),
        profile=os.environ.get(
            "AGENT_PLATFORM_DSH_PROFILE",
            "sdk",
        ),
        request_timeout_seconds=_optional_timeout(),
        env=runtime_env,
        notification_callback=(_lifecycle_observer()),
    )

    result = await executor.execute(
        WorkerExecutionRequest(
            goal=goal,
            workspace=Path.cwd(),
        )
    )

    sys.stdout.write(result.summary)

    if result.summary and not result.summary.endswith("\n"):
        sys.stdout.write("\n")

    return 0


def main() -> None:
    try:
        exit_code = asyncio.run(_run())
    except Exception as exc:
        print(
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
