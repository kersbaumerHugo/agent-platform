from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

DEFAULT_MODEL_ID = "fastino/GLiNER2.5-Decide"


class DecisionExtractor(Protocol):
    def classify_text(
        self,
        text: str,
        schema: dict[str, object],
        *,
        include_confidence: bool,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class DecisionOption:
    name: str
    description: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Decision option name must not be blank.")

        if not self.description.strip():
            raise ValueError("Decision option description must not be blank.")


@dataclass(frozen=True)
class DecisionResult:
    label: str
    confidence: float
    latency_ms: float

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("Decision label must not be blank.")

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Decision confidence must be between 0 and 1.")

        if self.latency_ms < 0:
            raise ValueError("Decision latency must not be negative.")


class GlinerDecisionModel:
    """Small local decision model backed by GLiNER2.5-Decide."""

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_MODEL_ID,
        device: str = "cpu",
        extractor: DecisionExtractor | None = None,
    ) -> None:
        if extractor is None:
            from gliner2 import AutoExtractor

            extractor = AutoExtractor.from_pretrained(
                model_id,
                map_location=device,
            )

        self._extractor = extractor
        self.model_id = model_id
        self.device = device

    def decide(
        self,
        *,
        text: str,
        options: tuple[DecisionOption, ...],
    ) -> DecisionResult:
        if not text.strip():
            raise ValueError("Decision text must not be blank.")

        if len(options) < 2:
            raise ValueError("At least two decision options are required.")

        names = tuple(option.name for option in options)

        if len(set(names)) != len(names):
            raise ValueError("Decision option names must be unique.")

        schema: dict[str, object] = {
            "decision": {"labels": {option.name: option.description for option in options}}
        }

        started = perf_counter()

        raw = self._extractor.classify_text(
            text,
            schema,
            include_confidence=True,
        )

        latency_ms = (perf_counter() - started) * 1000

        decision = raw.get("decision")

        if not isinstance(decision, dict):
            raise RuntimeError("GLiNER decision response does not contain a decision object.")

        label = decision.get("label")
        confidence = decision.get("confidence")

        if not isinstance(label, str):
            raise RuntimeError("GLiNER decision label is missing or invalid.")

        if label not in names:
            raise RuntimeError(f"GLiNER returned unknown decision label: {label!r}.")

        if not isinstance(confidence, int | float):
            raise RuntimeError("GLiNER decision confidence is missing or invalid.")

        return DecisionResult(
            label=label,
            confidence=float(confidence),
            latency_ms=latency_ms,
        )
