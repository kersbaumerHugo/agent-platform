from datetime import datetime

import httpx

from agent_platform.contracts.work_item import WorkItemProviderContract
from agent_platform.domain.work_item import WorkItem


class GitHubIssueWorkItemProvider(WorkItemProviderContract):
    """GitHub Issue adapter implementing the WorkItemProviderContract."""

    def __init__(
        self,
        repository: str,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        """Initialize the GitHub Issue provider.

        Args:
            repository: The owner/name of the repository (e.g., "owner/name").
            token: GitHub personal access token (optional).
            client: Optional httpx.AsyncClient to use (if provided, won't be closed).
            timeout_seconds: Timeout for HTTP requests.
        """
        # Validate repository has exactly two non-blank path components
        # Do not silently strip or normalize - both components must already be clean
        repo_parts = repository.split("/")
        if len(repo_parts) != 2:
            raise ValueError(
                f"repository must have exactly two path components, got {len(repo_parts)}"
            )

        for part in repo_parts:
            stripped_part = part.strip()
            if not part or not stripped_part:
                raise ValueError(
                    f"repository component must not be blank or whitespace, got '{part}'"
                )
            # Both components must already equal their stripped values
            if part != stripped_part:
                raise ValueError(f"repository component must not contain whitespace, got '{part}'")

        # Validate timeout
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")

        # Ensure self._client is ALWAYS an httpx.AsyncClient, never None
        # After this point, self._client will always have a valid AsyncClient instance
        if client is None:
            self._client = httpx.AsyncClient(timeout=timeout_seconds)
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False

        self.repository = repository
        self.token = token
        self.timeout_seconds = timeout_seconds

    @property
    def _headers(self) -> dict[str, str]:
        """Get the HTTP headers for requests."""
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def fetch(self, issue_number: int) -> WorkItem:
        """Fetch a WorkItem by issue number.

        Args:
            issue_number: The issue number to fetch.

        Returns:
            A WorkItem instance.

        Raises:
            ValueError: If issue_number < 1.
            ValueError: If response contains pull_request field.
            ValueError: If payload issue number doesn't match requested number.
            ValueError: If HTTP request fails.
        """
        # Reject issue_number < 1 BEFORE HTTP
        if issue_number < 1:
            raise ValueError("issue_number must be >= 1")

        # Build the URL
        url = f"https://api.github.com/repos/{self.repository}/issues/{issue_number}"

        # Make the request
        response = await self._client.get(url, headers=self._headers, timeout=self.timeout_seconds)
        response.raise_for_status()
        json_data = response.json()

        # Reject when pull_request field exists in the raw payload
        if "pull_request" in json_data:
            raise ValueError("Cannot fetch Pull Requests as WorkItems")

        # Reject when payload number != requested issue_number
        if json_data.get("number") != issue_number:
            raise ValueError(
                f"Payload issue number {json_data.get('number')} "
                f"doesn't match requested {issue_number}"
            )

        # Parse and map to WorkItem
        html_url = json_data.get("html_url")
        if not html_url:
            raise ValueError("html_url is required in GitHub response")

        title = json_data.get("title")
        if not title:
            raise ValueError("title is required in GitHub response")

        body = json_data.get("body") or ""

        # Parse updated_at
        updated_at: datetime | None = None
        if "updated_at" in json_data and json_data["updated_at"]:
            updated_at = datetime.fromisoformat(json_data["updated_at"].replace("Z", "+00:00"))

        return WorkItem(
            source="github",
            repository=self.repository,
            issue_number=json_data["number"],
            canonical_url=html_url,
            updated_at=updated_at,
            title=title,
            body=body,
        )

    async def aclose(self) -> None:
        """Close the client if this provider owns it."""
        if self._owns_client:
            await self._client.aclose()
