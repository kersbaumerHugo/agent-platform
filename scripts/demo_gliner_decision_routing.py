from __future__ import annotations

from agent_platform.adapters.models.gliner_decide import (
    DecisionOption,
    GlinerDecisionModel,
)
from agent_platform.application.model_routing import (
    ModelRoute,
    ModelRoutingPolicy,
)

OPTIONS = (
    DecisionOption(
        name="local_small",
        description=("Simple, low-risk task that a small local model can solve reliably."),
    ),
    DecisionOption(
        name="local_strong",
        description=("Moderately complex engineering task requiring stronger local reasoning."),
    ),
    DecisionOption(
        name="remote_strong",
        description=(
            "High-complexity or high-risk task requiring the strongest available reasoning model."
        ),
    ),
)


TASKS = (
    "Fix a typo in README.",
    ("Add a unit test for an existing pure function whose behavior is already documented."),
    (
        "Investigate a concurrency bug spanning several runtime "
        "modules, identify the root cause, implement the fix, "
        "and validate its architectural impact."
    ),
)


def main() -> None:
    print("Loading GLiNER2.5-Decide on CPU...")

    decision_model = GlinerDecisionModel(
        device="cpu",
    )

    routing_policy = ModelRoutingPolicy(
        routes=(
            ModelRoute(
                route="local_small",
                model="qwen-local-small",
            ),
            ModelRoute(
                route="local_strong",
                model="qwen-local-strong",
            ),
            ModelRoute(
                route="remote_strong",
                model="frontier-remote",
            ),
        )
    )

    print()
    print("Decision model ready.")
    print("=" * 78)

    for task in TASKS:
        decision = decision_model.decide(
            text=task,
            options=OPTIONS,
        )

        selected_model = routing_policy.resolve(
            decision.label,
        )

        print(f"TASK       : {task}")
        print(f"DECISION   : {decision.label}")
        print(f"CONFIDENCE : {decision.confidence:.3f}")
        print(f"MODEL      : {selected_model}")
        print(f"LATENCY    : {decision.latency_ms:.1f} ms")
        print("-" * 78)


if __name__ == "__main__":
    main()
