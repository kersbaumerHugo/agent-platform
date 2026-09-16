from enum import StrEnum
from hashlib import sha256
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContextRole(StrEnum):
    SHARED = "shared"
    DELIVERY = "delivery"
    SUBJECT = "subject"


class ContextRef(BaseModel):
    role: ContextRole
    namespace: str = Field(min_length=1)


def content_sha256(content: str) -> str:
    digest = sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class ContextProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_revision: str | None = None
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ContextItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    context: ContextRef
    provenance: ContextProvenance

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        if self.provenance.content_hash != content_sha256(self.content):
            raise ValueError("ContextItem provenance content_hash must match item content.")
        return self


class ContextContribution(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)
    context: ContextRef
    items: tuple[ContextItem, ...] = ()

    @model_validator(mode="after")
    def validate_items(self) -> Self:
        for item in self.items:
            if item.context != self.context:
                raise ValueError("ContextContribution items must share the contribution context.")
            if item.provenance.provider != self.provider:
                raise ValueError("ContextContribution items must share the contribution provider.")
        return self


class ContextSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: ContextRef
    items: tuple[ContextItem, ...] = ()

    @model_validator(mode="after")
    def validate_items(self) -> Self:
        if any(item.context != self.context for item in self.items):
            raise ValueError("ContextSection items must share the section context.")
        return self


class ContextBundle(BaseModel):
    model_config = ConfigDict(frozen=True)

    sections: tuple[ContextSection, ...] = ()

    @model_validator(mode="after")
    def validate_unique_sections(self) -> Self:
        context_keys = [
            (section.context.role, section.context.namespace) for section in self.sections
        ]
        if len(context_keys) != len(set(context_keys)):
            raise ValueError("ContextBundle sections must be unique by role and namespace.")
        return self
