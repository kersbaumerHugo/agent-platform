from __future__ import annotations

from agent_platform.adapters.models.gliner_decide import (
    DecisionOption,
    GlinerDecisionModel,
)

OPTIONS = (
    DecisionOption(
        name="call_now",
        description=(
            "High-value lead with strong buying intent, clear fit, "
            "and enough context to justify immediate outreach."
        ),
    ),
    DecisionOption(
        name="defer",
        description=(
            "Potentially relevant lead, but timing or available context "
            "does not justify immediate outreach."
        ),
    ),
    DecisionOption(
        name="skip",
        description=(
            "Low-value or poor-fit lead where outreach is unlikely to produce useful results."
        ),
    ),
    DecisionOption(
        name="human_review",
        description=(
            "Ambiguous, sensitive, or unusual lead that should be "
            "reviewed by a human before outreach."
        ),
    ),
)


LEADS = (
    (
        "CTO of a 120-person SaaS company. Recently posted that their "
        "engineering team is struggling with AI agent reliability and "
        "model costs. The company is actively hiring AI engineers."
    ),
    (
        "Junior developer at a small agency. No purchasing authority, "
        "no public indication of interest in AI infrastructure."
    ),
    (
        "VP Engineering at an enterprise company. Interested in AI agents, "
        "but publicly stated that their platform migration will only start "
        "next quarter."
    ),
    (
        "Executive at a regulated healthcare company requesting information "
        "about autonomous AI systems handling sensitive patient workflows."
    ),
)


def main() -> None:
    print("Loading GLiNER2.5-Decide on CPU...")

    model = GlinerDecisionModel(
        device="cpu",
    )

    print()
    print("Cold-call decision model ready.")
    print("=" * 78)

    for lead in LEADS:
        result = model.decide(
            text=lead,
            options=OPTIONS,
        )

        print(f"LEAD       : {lead}")
        print(f"DECISION   : {result.label}")
        print(f"CONFIDENCE : {result.confidence:.3f}")
        print(f"LATENCY    : {result.latency_ms:.1f} ms")
        print("-" * 78)


if __name__ == "__main__":
    main()
