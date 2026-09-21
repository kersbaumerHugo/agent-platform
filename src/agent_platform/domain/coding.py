from __future__ import annotations

import re
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

_GIT_SHA1_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_CHANGE_SET_IDENTITY_PATTERN = re.compile(r"^v1:sha256:[0-9a-f]{64}$")


class CodingVerificationOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


class CodingPublicationOutcome(StrEnum):
    PUBLISHED = "published"


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


class CodingResult(BaseModel):
    """Safe platform-owned correlation result for one supervised coding task."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    task_id: UUID
    execution_id: UUID
    base_revision: str
    change_set_identity: str
    changed_paths: tuple[str, ...] = Field(min_length=1)
    verification_profile_version: str = Field(min_length=1)
    verification_outcome: CodingVerificationOutcome
    publication_outcome: CodingPublicationOutcome
    publication_reference: str = Field(min_length=1)
    pull_request_number: int | None = Field(
        default=None,
        ge=1,
    )

    @field_validator("base_revision")
    @classmethod
    def validate_base_revision(cls, value: str) -> str:
        normalized = value.strip().lower()

        if not _GIT_SHA1_PATTERN.fullmatch(normalized):
            raise ValueError("CodingResult base_revision must be a full 40-character Git SHA-1.")

        return normalized

    @field_validator("change_set_identity")
    @classmethod
    def validate_change_set_identity(cls, value: str) -> str:
        normalized = value.strip()

        if not _CHANGE_SET_IDENTITY_PATTERN.fullmatch(normalized):
            raise ValueError(
                "CodingResult change_set_identity must use v1:sha256:<64 lowercase hex>."
            )

        return normalized

    @field_validator("changed_paths")
    @classmethod
    def normalize_changed_paths(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not path.strip() for path in value):
            raise ValueError("CodingResult changed_paths must not contain blank paths.")

        if len(value) != len(set(value)):
            raise ValueError("CodingResult changed_paths must be unique.")

        return tuple(sorted(value))

    @field_validator(
        "verification_profile_version",
        "publication_reference",
    )
    @classmethod
    def normalize_nonblank_text(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("CodingResult text fields must not be blank.")

        return normalized
