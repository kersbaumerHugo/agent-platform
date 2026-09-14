from __future__ import annotations

import asyncio
import re
import subprocess

from agent_platform.adapters.github.proposal import (
    PullRequestResult,
    PullRequestSpec,
)

_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

_PULL_REQUEST_URL_PATTERN = re.compile(
    r"^https://github\.com/"
    r"[A-Za-z0-9_.-]+/"
    r"[A-Za-z0-9_.-]+/"
    r"pull/[0-9]+$"
)


class GitHubCliError(RuntimeError):
    pass


class GitHubCliPullRequestClient:
    """Trusted-side GitHub client with PR-creation capability only."""

    def __init__(
        self,
        repository: str,
        *,
        gh_binary: str = "gh",
        timeout_seconds: float = 60.0,
    ) -> None:
        parts = repository.split("/")

        if (
            not _REPOSITORY_PATTERN.fullmatch(repository)
            or len(parts) != 2
            or any(part.startswith("-") for part in parts)
        ):
            raise ValueError("repository must use safe owner/name format.")

        if not gh_binary.strip():
            raise ValueError("gh_binary must not be empty.")

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        self._repository = repository
        self._gh_binary = gh_binary
        self._timeout_seconds = timeout_seconds

    async def create_pull_request(
        self,
        spec: PullRequestSpec,
    ) -> PullRequestResult:
        return await asyncio.to_thread(
            self._create_pull_request_sync,
            spec,
        )

    def _create_pull_request_sync(
        self,
        spec: PullRequestSpec,
    ) -> PullRequestResult:
        self._validate_spec(spec)

        try:
            result = subprocess.run(
                [
                    self._gh_binary,
                    "pr",
                    "create",
                    "--repo",
                    self._repository,
                    "--base",
                    spec.base_branch,
                    "--head",
                    spec.head_branch,
                    "--title",
                    spec.title,
                    "--body-file",
                    "-",
                ],
                input=spec.body,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitHubCliError("GitHub PR creation timed out.") from exc
        except OSError as exc:
            raise GitHubCliError("Unable to execute GitHub CLI.") from exc

        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown GitHub CLI error"

            raise GitHubCliError(f"GitHub PR creation failed: {detail}")

        reference = result.stdout.strip()

        if not _PULL_REQUEST_URL_PATTERN.fullmatch(reference):
            raise GitHubCliError("GitHub CLI returned an unexpected PR reference.")

        return PullRequestResult(
            reference=reference,
        )

    @staticmethod
    def _validate_spec(
        spec: PullRequestSpec,
    ) -> None:
        if not spec.head_branch.strip():
            raise ValueError("head_branch must not be empty.")

        if not spec.base_branch.strip():
            raise ValueError("base_branch must not be empty.")

        if spec.head_branch.startswith("-"):
            raise ValueError("head_branch must not start with '-'.")

        if spec.base_branch.startswith("-"):
            raise ValueError("base_branch must not start with '-'.")

        if not spec.title.strip():
            raise ValueError("title must not be empty.")
