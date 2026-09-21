from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class RepoWiseContextItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    target: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class RepoWiseContextSnapshot(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    items: tuple[RepoWiseContextItem, ...]
    indexed_commit: str | None = None
    stale_warning: str | None = None


class RepoWiseClientContract(Protocol):
    async def get_context(
        self,
        targets: tuple[str, ...],
    ) -> RepoWiseContextSnapshot: ...
