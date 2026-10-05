from typing import Any

import pytest

from agent_platform.adapters.models.gliner_decide import (
    DecisionOption,
    GlinerDecisionModel,
)


class FakeExtractor:
    def __init__(
        self,
        result: dict[str, Any],
    ) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, object], bool]] = []

    def classify_text(
        self,
        text: str,
        schema: dict[str, object],
        *,
        include_confidence: bool,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                text,
                schema,
                include_confidence,
            )
        )
        return self.result


OPTIONS = (
    DecisionOption(
        name="local_small",
        description="Simple low-risk task.",
    ),
    DecisionOption(
        name="local_strong",
        description="Task requiring stronger local reasoning.",
    ),
    DecisionOption(
        name="remote_strong",
        description="Complex task requiring strongest reasoning.",
    ),
)


def test_decides_using_runtime_options() -> None:
    extractor = FakeExtractor(
        {
            "decision": {
                "label": "local_small",
                "confidence": 0.91,
            }
        }
    )

    model = GlinerDecisionModel(
        extractor=extractor,
    )

    result = model.decide(
        text="Fix a typo in README.",
        options=OPTIONS,
    )

    assert result.label == "local_small"
    assert result.confidence == pytest.approx(0.91)
    assert result.latency_ms >= 0

    assert extractor.calls == [
        (
            "Fix a typo in README.",
            {
                "decision": {
                    "labels": {
                        "local_small": "Simple low-risk task.",
                        "local_strong": ("Task requiring stronger local reasoning."),
                        "remote_strong": ("Complex task requiring strongest reasoning."),
                    }
                }
            },
            True,
        )
    ]


def test_rejects_unknown_model_decision() -> None:
    model = GlinerDecisionModel(
        extractor=FakeExtractor(
            {
                "decision": {
                    "label": "unknown",
                    "confidence": 0.9,
                }
            }
        )
    )

    with pytest.raises(
        RuntimeError,
        match="unknown decision label",
    ):
        model.decide(
            text="Do something.",
            options=OPTIONS,
        )


def test_requires_multiple_options() -> None:
    model = GlinerDecisionModel(extractor=FakeExtractor({}))

    with pytest.raises(
        ValueError,
        match="At least two",
    ):
        model.decide(
            text="Do something.",
            options=(OPTIONS[0],),
        )


def test_requires_unique_option_names() -> None:
    model = GlinerDecisionModel(extractor=FakeExtractor({}))

    duplicated = (
        DecisionOption(
            name="small",
            description="One.",
        ),
        DecisionOption(
            name="small",
            description="Two.",
        ),
    )

    with pytest.raises(
        ValueError,
        match="must be unique",
    ):
        model.decide(
            text="Do something.",
            options=duplicated,
        )
