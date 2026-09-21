from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ToolDefinition(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)

    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class ToolRequest(BaseModel):
    run_id: UUID
    principal_id: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("principal_id")
    @classmethod
    def normalize_principal_id(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            raise ValueError("ToolRequest principal_id must not be blank.")

        return normalized


class ToolResult(BaseModel):
    run_id: UUID
    tool_name: str = Field(min_length=1)
    output: dict[str, Any]
