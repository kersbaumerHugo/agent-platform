from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from agent_platform.trust.verification import (
    VerificationOutcome,
    VerificationResult,
    VerificationStepResult,
)
from agent_platform.trust.verification_profile import (
    AuthoritativeVerificationProfile,
    VerificationStep,
)


class VerificationProcessOutcome(StrEnum):
    EXITED = "exited"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass(frozen=True)
class VerificationProcessResult:
    outcome: VerificationProcessOutcome
    exit_code: int | None


class VerificationProcessRunner(Protocol):
    async def run(
        self,
        *,
        workspace: Path,
        argv: tuple[str, ...],
    ) -> VerificationProcessResult: ...


class SubprocessVerificationProcessRunner:
    """Process lifecycle primitive for an already-isolated verifier environment.

    This class deliberately uses no shell and passes a minimal environment. It is
    not, by itself, a filesystem or network security boundary.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 300.0,
        terminate_grace_seconds: float = 5.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        if terminate_grace_seconds <= 0:
            raise ValueError("terminate_grace_seconds must be greater than zero.")

        self._timeout_seconds = timeout_seconds
        self._terminate_grace_seconds = terminate_grace_seconds

    async def run(
        self,
        *,
        workspace: Path,
        argv: tuple[str, ...],
    ) -> VerificationProcessResult:
        if not argv:
            raise ValueError("argv must not be empty.")

        if any(not part or "\x00" in part for part in argv):
            raise ValueError("argv contains an invalid argument.")

        workspace = self._resolve_workspace(workspace)

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=workspace,
                env=self._environment(),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            return VerificationProcessResult(
                outcome=VerificationProcessOutcome.ERROR,
                exit_code=None,
            )

        try:
            exit_code = await asyncio.wait_for(
                process.wait(),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            await self._terminate_process_group(process)
            return VerificationProcessResult(
                outcome=VerificationProcessOutcome.TIMEOUT,
                exit_code=None,
            )
        except asyncio.CancelledError:
            await self._terminate_process_group(process)
            raise

        return VerificationProcessResult(
            outcome=VerificationProcessOutcome.EXITED,
            exit_code=exit_code,
        )

    @staticmethod
    def _resolve_workspace(workspace: Path) -> Path:
        if workspace.is_symlink():
            raise ValueError("Verification workspace must not be a symlink.")

        try:
            resolved = workspace.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError("Verification workspace must exist.") from exc

        if not resolved.is_dir():
            raise ValueError("Verification workspace must be a directory.")

        return resolved

    @staticmethod
    def _environment() -> dict[str, str]:
        path = os.environ.get("PATH", "")

        if not path:
            raise RuntimeError("PATH is required for verification execution.")

        environment = {
            "PATH": path,
            "HOME": "/tmp",
            "TMPDIR": "/tmp",
            "PYTHONUTF8": "1",
        }

        for name in ("LANG", "LC_ALL", "VIRTUAL_ENV"):
            value = os.environ.get(name)
            if value:
                environment[name] = value

        return environment

    async def _terminate_process_group(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        if process.returncode is not None:
            return

        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        try:
            await asyncio.wait_for(
                process.wait(),
                timeout=self._terminate_grace_seconds,
            )
            return
        except TimeoutError:
            pass

        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

        await process.wait()


class ProfileVerificationExecutor:
    """Execute every authoritative profile step and return complete evidence."""

    def __init__(
        self,
        *,
        runner: VerificationProcessRunner,
    ) -> None:
        self._runner = runner

    async def execute(
        self,
        *,
        workspace: Path,
        profile: AuthoritativeVerificationProfile,
    ) -> VerificationResult:
        results: list[VerificationStepResult] = []

        for step in profile.steps:
            process_result = await self._runner.run(
                workspace=workspace,
                argv=step.argv,
            )
            results.append(self._step_result(step, process_result))

        outcome = self._overall_outcome(results)

        return VerificationResult(
            profile_version=profile.version,
            outcome=outcome,
            reason_code=self._reason_code(outcome),
            steps=tuple(results),
        )

    @staticmethod
    def _step_result(
        step: VerificationStep,
        process_result: VerificationProcessResult,
    ) -> VerificationStepResult:
        if process_result.outcome is VerificationProcessOutcome.TIMEOUT:
            return VerificationStepResult(
                check=step.check,
                outcome=VerificationOutcome.ERROR,
                exit_code=None,
                summary="verification_step_timeout",
            )

        if process_result.outcome is VerificationProcessOutcome.ERROR:
            return VerificationStepResult(
                check=step.check,
                outcome=VerificationOutcome.ERROR,
                exit_code=None,
                summary="verification_step_execution_error",
            )

        if process_result.exit_code == 0:
            return VerificationStepResult(
                check=step.check,
                outcome=VerificationOutcome.PASS,
                exit_code=0,
                summary="verification_step_passed",
            )

        if process_result.exit_code is None:
            return VerificationStepResult(
                check=step.check,
                outcome=VerificationOutcome.ERROR,
                exit_code=None,
                summary="verification_step_missing_exit_code",
            )

        return VerificationStepResult(
            check=step.check,
            outcome=VerificationOutcome.FAIL,
            exit_code=process_result.exit_code,
            summary="verification_step_failed",
        )

    @staticmethod
    def _overall_outcome(
        results: list[VerificationStepResult],
    ) -> VerificationOutcome:
        if any(result.outcome is VerificationOutcome.ERROR for result in results):
            return VerificationOutcome.ERROR

        if any(result.outcome is VerificationOutcome.FAIL for result in results):
            return VerificationOutcome.FAIL

        return VerificationOutcome.PASS

    @staticmethod
    def _reason_code(outcome: VerificationOutcome) -> str:
        if outcome is VerificationOutcome.PASS:
            return "all_checks_passed"

        if outcome is VerificationOutcome.FAIL:
            return "check_failed"

        return "verification_error"
