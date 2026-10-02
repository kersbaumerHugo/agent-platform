from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from agent_platform.trust.diagnostic_verification import (
    TrustedDiagnosticVerificationClient,
)

_DIAGNOSTIC_SOCKET_ENV = "AGENT_PLATFORM_DIAGNOSTIC_VERIFIER_SOCKET"

_SELF_VERIFICATION_COMMAND = (
    "python",
    "-m",
    "pytest",
    "-q",
)


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
            f"timed_out: "
            f"{str(self.timed_out).lower()}\n"
            "output:\n"
            f"{self.output}"
        )


async def run_worker_self_verification(
    workspace: Path,
) -> WorkerSelfVerificationResult:
    resolved = workspace.resolve(strict=True)

    if not resolved.is_dir():
        raise ValueError("Worker workspace must be a directory.")

    raw_socket_path = os.environ.get(
        _DIAGNOSTIC_SOCKET_ENV,
        "",
    ).strip()

    if not raw_socket_path:
        raise RuntimeError("Trusted diagnostic verifier socket is not configured.")

    socket_path = Path(raw_socket_path)

    if not socket_path.is_absolute():
        raise RuntimeError("Trusted diagnostic verifier socket must be an absolute path.")

    client = TrustedDiagnosticVerificationClient(
        socket_path=socket_path,
    )

    result = await client.verify()

    return WorkerSelfVerificationResult(
        command=_SELF_VERIFICATION_COMMAND,
        exit_code=result.exit_code,
        output=result.output,
        timed_out=result.timed_out,
    )


def build_self_repair_goal(
    *,
    original_goal: str,
    verification: WorkerSelfVerificationResult,
    phase_limited: bool = False,
) -> str:
    if phase_limited:
        trigger = (
            "The previous implementation attempt "
            "reached its model-call phase limit "
            "before completing."
        )
    else:
        trigger = (
            "Deterministic Worker self-verification failed after your previous implementation."
        )

    return (
        f"{original_goal.strip()}\\n\\n"
        f"{trigger} "
        "This is the single bounded self-repair "
        "attempt for this sandbox execution. "
        "Repair the existing workspace rather "
        "than starting over.\\n\\n"
        "Self-verification evidence:\\n"
        f"{verification.repair_feedback()}\\n\\n"
        "Preserve the requested task scope. "
        "Do not weaken or delete tests merely to "
        "obtain a passing result. Run relevant "
        "verification after repairing. Do not "
        "commit, push, or create pull requests."
    )
