from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ModelMessage(BaseModel):
    role: MessageRole
    content: str = Field(min_length=1)


class ModelRequest(BaseModel):
    run_id: UUID
    messages: list[ModelMessage] = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelResult(BaseModel):
    provider: str
    model: str
    output: str
    provider_request_id: str | None = None
    finish_reason: str | None = None
    usage: TokenUsage | None = None
