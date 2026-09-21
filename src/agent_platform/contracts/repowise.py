from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class RepoWiseSymbol(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    signature: str = Field(min_length=1)
    line: int | None = Field(
        default=None,
        ge=1,
    )


class RepoWiseContextItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    target: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    symbols: tuple[RepoWiseSymbol, ...] = ()


class RepoWiseContextSnapshot(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    items: tuple[RepoWiseContextItem, ...]
    indexed_commit: str | None = None
    stale: bool = False


class RepoWiseClientContract(Protocol):
    async def get_context(
        self,
        targets: tuple[str, ...],
    ) -> RepoWiseContextSnapshot: ...
