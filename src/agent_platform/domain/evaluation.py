from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, FiniteFloat


class EvaluationOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


class EvaluationCase(BaseModel):
    case_id: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    case_id: str = Field(min_length=1)
    evaluator: str = Field(min_length=1)
    outcome: EvaluationOutcome
    reason_code: str = Field(min_length=1)
    metrics: dict[str, FiniteFloat] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
