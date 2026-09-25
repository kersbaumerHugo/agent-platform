from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkItem(BaseModel):
    """Immutable provider-neutral work item referencing an issue."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    source: str = Field(..., min_length=1)
    repository: str = Field(..., min_length=1)
    issue_number: int = Field(..., ge=1)
    canonical_url: str = Field(..., min_length=1)
    updated_at: datetime | None = None
    title: str = Field(..., min_length=1)
    body: str = Field(default="", min_length=0)

    @model_validator(mode="after")
    def validate_fields(self) -> Self:
        # Reject blank values for required fields (after stripping whitespace)
        if not self.source.strip():
            raise ValueError("source must not be blank")
        if not self.repository.strip():
            raise ValueError("repository must not be blank")
        if not self.canonical_url.strip():
            raise ValueError("canonical_url must not be blank")
        if not self.title.strip():
            raise ValueError("title must not be blank")
        # body is required but may be empty
        return self
