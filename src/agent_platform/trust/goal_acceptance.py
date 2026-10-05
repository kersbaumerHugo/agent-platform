from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GoalAcceptanceOutcome(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"


@dataclass(frozen=True)
class GoalAcceptanceResult:
    outcome: GoalAcceptanceOutcome
    reason_code: str

    def __post_init__(self) -> None:
        if not self.reason_code.strip():
            raise ValueError("reason_code must not be empty.")

    @property
    def accepted(self) -> bool:
        return self.outcome is GoalAcceptanceOutcome.ACCEPT


class GoalAcceptanceEvaluator:
    """Evaluate trusted task-completion evidence."""

    def evaluate(
        self,
        *,
        changed_paths: tuple[str, ...],
    ) -> GoalAcceptanceResult:
        normalized = tuple(path.strip() for path in changed_paths if path.strip())

        if not normalized:
            return GoalAcceptanceResult(
                outcome=GoalAcceptanceOutcome.REJECT,
                reason_code="required_change_missing",
            )

        return GoalAcceptanceResult(
            outcome=GoalAcceptanceOutcome.ACCEPT,
            reason_code="change_present",
        )
