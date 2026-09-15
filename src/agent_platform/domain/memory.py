from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field


class MemoryScope(BaseModel):
    namespace: str = Field(min_length=1)


class MemoryRecord(BaseModel):
    id: UUID
    scope: MemoryScope
    content: str = Field(min_length=1)
    created_at: AwareDatetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalQuery(BaseModel):
    scope: MemoryScope
    text: str = Field(min_length=1)
    limit: int = Field(default=5, gt=0)


class RetrievalHit(BaseModel):
    memory: MemoryRecord
    score: float = Field(allow_inf_nan=False)
    rank: int = Field(gt=0)


class RetrievalDecision(StrEnum):
    ACCEPT = "accept"
    ABSTAIN = "abstain"


class RetrievalAcceptanceDecision(BaseModel):
    decision: RetrievalDecision
    reason_code: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
