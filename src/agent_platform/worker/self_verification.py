from __future__ import annotations

import asyncio
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

_MAX_OUTPUT_CHARS = 8192
_DEFAULT_TIMEOUT_SECONDS = 90.0


@dataclass(frozen=True)
class WorkerSelfVerificationResult:
    command: tuple[str, ...]
    exit_code: int | None
    output: str
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return not self.timed_out and self.exit_code == 0

    def repair_feedback(self) -> str:
        exit_code = "none" if self.exit_code is None else str(self.exit_code)

        return (
            f"command: {shlex.join(self.command)}\n"
            f"exit_code: {exit_code}\n"
            f"timed_out: {str(self.timed_out).lower()}\n"
            "output:\n"
            f"{self.output}"
        )


async def run_worker_self_verification(
    workspace: Path,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> WorkerSelfVerificationResult:
    resolved = workspace.resolve(strict=True)

    if not resolved.is_dir():
        raise ValueError("Worker workspace must be a directory.")

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero.")

    command = (
        sys.executable,
        "-m",
        "pytest",
        "-q",
    )

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=resolved,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        process.kill()
        stdout, _ = await process.communicate()

        return WorkerSelfVerificationResult(
            command=command,
            exit_code=None,
            output=_bounded_output(stdout),
            timed_out=True,
        )

    return WorkerSelfVerificationResult(
        command=command,
        exit_code=process.returncode,
        output=_bounded_output(stdout),
    )


def build_self_repair_goal(
    *,
    original_goal: str,
    verification: WorkerSelfVerificationResult,
) -> str:
    return (
        f"{original_goal.strip()}\n\n"
        "Deterministic Worker self-verification failed after your previous "
        "implementation. This is the single bounded self-repair attempt for "
        "this sandbox execution. Repair the existing workspace rather than "
        "starting over.\n\n"
        "Self-verification evidence:\n"
        f"{verification.repair_feedback()}\n\n"
        "Preserve the requested task scope. Do not weaken or delete tests "
        "merely to obtain a passing result. Run relevant verification after "
        "repairing. Do not commit, push, or create pull requests."
    )


def _bounded_output(raw: bytes) -> str:
    decoded = raw.decode(
        "utf-8",
        errors="replace",
    ).strip()

    if len(decoded) <= _MAX_OUTPUT_CHARS:
        return decoded

    return decoded[-_MAX_OUTPUT_CHARS:]
