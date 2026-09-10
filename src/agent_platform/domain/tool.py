from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)

    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class ToolRequest(BaseModel):
    run_id: UUID
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    run_id: UUID
    tool_name: str = Field(min_length=1)
    output: dict[str, Any]
