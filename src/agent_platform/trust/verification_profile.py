from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class VerificationCheck(StrEnum):
    """Stable identifiers for authoritative M12 V0 verification checks."""

    SYNTAX = "syntax"
    RUFF_LINT = "ruff_lint"
    RUFF_FORMAT = "ruff_format"
    TYPECHECK = "typecheck"
    TEST = "test"
    PACKAGE = "package"
    DIFF_CHECK = "diff_check"


@dataclass(frozen=True)
class VerificationStep:
    """One platform-owned verification command expressed as argv, never shell text."""

    check: VerificationCheck
    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.argv:
            raise ValueError("VerificationStep argv must not be empty.")

        if any(not part or "\x00" in part for part in self.argv):
            raise ValueError("VerificationStep argv contains an invalid argument.")


@dataclass(frozen=True, init=False)
class AuthoritativeVerificationProfile:
    """Immutable authoritative verification profile for M12 V0."""

    version: str = "m12-v0"

    steps: tuple[VerificationStep, ...] = (
        VerificationStep(
            check=VerificationCheck.SYNTAX,
            argv=(
                "python",
                "-m",
                "compileall",
                "-q",
                "src",
                "tests",
                "scripts",
            ),
        ),
        VerificationStep(
            check=VerificationCheck.RUFF_LINT,
            argv=(
                "python",
                "-m",
                "ruff",
                "check",
                "src",
                "tests",
                "scripts",
            ),
        ),
        VerificationStep(
            check=VerificationCheck.RUFF_FORMAT,
            argv=(
                "python",
                "-m",
                "ruff",
                "format",
                "--check",
                "src",
                "tests",
                "scripts",
            ),
        ),
        VerificationStep(
            check=VerificationCheck.TYPECHECK,
            argv=(
                "python",
                "-m",
                "mypy",
                "src",
            ),
        ),
        VerificationStep(
            check=VerificationCheck.TEST,
            argv=(
                "python",
                "-m",
                "pytest",
                "-q",
            ),
        ),
        VerificationStep(
            check=VerificationCheck.PACKAGE,
            argv=(
                "python",
                "-m",
                "build",
            ),
        ),
        VerificationStep(
            check=VerificationCheck.DIFF_CHECK,
            argv=(
                "git",
                "diff",
                "--check",
            ),
        ),
    )
