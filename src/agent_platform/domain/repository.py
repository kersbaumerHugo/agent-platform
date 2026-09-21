from pydantic import BaseModel, ConfigDict, Field


class RepositoryInspectionRequest(BaseModel):
    """Request structured evidence about repository targets."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    targets: tuple[str, ...] = Field(
        min_length=1,
    )


class RepositorySymbol(BaseModel):
    """One provider-independent repository symbol."""

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


class RepositoryEvidence(BaseModel):
    """One provider-independent repository evidence item."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    target: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    symbols: tuple[RepositorySymbol, ...] = ()

    source_reference: str = Field(min_length=1)


class RepositoryInspectionResult(BaseModel):
    """Structured repository evidence returned by an inspection backend."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    evidence: tuple[RepositoryEvidence, ...]
    indexed_revision: str | None = None
    stale: bool = False
