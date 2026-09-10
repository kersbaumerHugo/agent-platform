from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ModelToolDefinition(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: dict[str, Any]


class ModelToolCall(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)

    # Keep the provider/OpenAI-compatible raw JSON string.
    # The runtime owns parsing of model-generated arguments.
    arguments: str


class ModelMessage(BaseModel):
    role: MessageRole

    content: str | None = None

    tool_call_id: str | None = None
    tool_calls: list[ModelToolCall] = Field(default_factory=list)

    reasoning_content: str | None = None


class ModelRequest(BaseModel):
    run_id: UUID

    messages: list[ModelMessage] = Field(min_length=1)

    tools: list[ModelToolDefinition] = Field(default_factory=list)

    temperature: float | None = Field(
        default=None,
        ge=0,
        le=2,
    )

    max_tokens: int | None = Field(
        default=None,
        gt=0,
    )


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelResult(BaseModel):
    provider: str
    model: str

    output: str = ""

    tool_calls: list[ModelToolCall] = Field(default_factory=list)

    reasoning_content: str | None = None

    provider_request_id: str | None = None
    finish_reason: str | None = None
    usage: TokenUsage | None = None
