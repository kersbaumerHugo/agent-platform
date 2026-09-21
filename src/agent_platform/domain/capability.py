from pydantic import BaseModel, ConfigDict, Field


class CapabilityDefinition(BaseModel):
    """Stable platform-owned metadata for one executable capability."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
