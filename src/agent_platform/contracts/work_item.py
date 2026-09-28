from typing import Protocol

from agent_platform.domain.work_item import WorkItem


class WorkItemProviderContract(Protocol):
    """Provider-neutral contract for fetching WorkItem from an issue number."""

    async def fetch(self, issue_number: int) -> WorkItem:
        """Fetch a WorkItem by issue number.

        Args:
            issue_number: The issue number to fetch.

        Returns:
            A WorkItem instance.
        """
        ...
