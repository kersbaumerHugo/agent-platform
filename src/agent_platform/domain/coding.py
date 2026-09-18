from __future__ import annotations

import re
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

_GIT_SHA1_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class CodingTask(BaseModel):
    """Platform-owned contract for one supervised coding request."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    task_id: UUID = Field(default_factory=uuid4)
    goal: str = Field(min_length=1)
    expected_base_revision: str

    @field_validator("goal")
    @classmethod
    def normalize_goal(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("CodingTask goal must not be blank.")

        return normalized

    @field_validator("expected_base_revision")
    @classmethod
    def validate_expected_base_revision(cls, value: str) -> str:
        normalized = value.strip().lower()

        if not _GIT_SHA1_PATTERN.fullmatch(normalized):
            raise ValueError(
                "CodingTask expected_base_revision must be a full 40-character Git SHA-1."
            )

        return normalized
