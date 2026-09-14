from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

DEFAULT_PROTECTED_PATTERNS = (
    ".github/**",
    "pyproject.toml",
    "setup.cfg",
    "tox.ini",
    "pytest.ini",
    "ruff.toml",
    ".ruff.toml",
    "mypy.ini",
    ".mypy.ini",
    "conftest.py",
    "**/conftest.py",
    "src/agent_platform/trust/**",
    "src/agent_platform/adapters/git/**",
    "src/agent_platform/adapters/github/**",
    "tests/trusted/**",
)


@dataclass(frozen=True)
class ChangePolicyDecision:
    allowed: bool
    blocked_paths: tuple[str, ...]
    reason_code: str


class ChangePolicy:
    def __init__(
        self,
        protected_patterns: tuple[str, ...] = DEFAULT_PROTECTED_PATTERNS,
    ) -> None:
        if not protected_patterns:
            raise ValueError("ChangePolicy requires protected patterns.")

        self._protected_patterns = protected_patterns

    def evaluate(
        self,
        changed_paths: Iterable[str],
    ) -> ChangePolicyDecision:
        blocked: list[str] = []

        for raw_path in changed_paths:
            path = self._normalize_path(raw_path)

            if any(fnmatchcase(path, pattern) for pattern in self._protected_patterns):
                blocked.append(path)

        if blocked:
            return ChangePolicyDecision(
                allowed=False,
                blocked_paths=tuple(sorted(set(blocked))),
                reason_code="protected_path_modified",
            )

        return ChangePolicyDecision(
            allowed=True,
            blocked_paths=(),
            reason_code="allowed",
        )

    @staticmethod
    def _normalize_path(raw_path: str) -> str:
        if not raw_path.strip():
            raise ValueError("Changed path must not be empty.")

        candidate = raw_path.replace("\\", "/")
        path = PurePosixPath(candidate)

        if path.is_absolute():
            raise ValueError("Changed path must be repository-relative.")

        if ".." in path.parts:
            raise ValueError("Changed path must not contain '..'.")

        normalized = path.as_posix()

        if normalized == ".":
            raise ValueError("Changed path must reference a file.")

        return normalized
