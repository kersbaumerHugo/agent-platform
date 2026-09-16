from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_platform.domain.context import content_sha256


class RenderedContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    renderer: str = Field(min_length=1)
    version: str = Field(min_length=1)
    text: str
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        if self.content_hash != content_sha256(self.text):
            raise ValueError("RenderedContext content_hash must match rendered text.")
        return self
