import pytest
from pydantic import ValidationError

from agent_platform.application.context_budget import (
    DeterministicContextBudgetPolicy,
    Utf8ByteTokenEstimator,
)
from agent_platform.contracts.context import (
    ContextBudgetPolicyContract,
    TokenEstimatorContract,
)
from agent_platform.domain.context import (
    ContextBundle,
    ContextItem,
    ContextProvenance,
    ContextRef,
    ContextRole,
    ContextSection,
    content_sha256,
)
from agent_platform.domain.context_budget import ContextBudget


def make_item(
    *,
    item_id: str,
    content: str,
    context: ContextRef,
) -> ContextItem:
    return ContextItem(
        item_id=item_id,
        content=content,
        kind="fact",
        context=context,
        provenance=ContextProvenance(
            provider="memory",
            source_id=item_id,
            content_hash=content_sha256(content),
        ),
    )


def make_bundle() -> ContextBundle:
    shared = ContextRef(
        role=ContextRole.SHARED,
        namespace="global",
    )
    delivery = ContextRef(
        role=ContextRole.DELIVERY,
        namespace="app:linkedin",
    )
    subject = ContextRef(
        role=ContextRole.SUBJECT,
        namespace="project:homelab",
    )

    return ContextBundle(
        sections=(
            ContextSection(
                context=shared,
                items=(
                    make_item(
                        item_id="shared:1",
                        content="aaaa",
                        context=shared,
                    ),
                ),
            ),
            ContextSection(
                context=delivery,
                items=(
                    make_item(
                        item_id="delivery:1",
                        content="bbbbbbbb",
                        context=delivery,
                    ),
                ),
            ),
            ContextSection(
                context=subject,
                items=(
                    make_item(
                        item_id="subject:1",
                        content="cccc",
                        context=subject,
                    ),
                ),
            ),
        )
    )


def assert_token_estimator_contract(
    estimator: TokenEstimatorContract,
) -> None:
    assert estimator.version


def assert_budget_policy_contract(
    policy: ContextBudgetPolicyContract,
) -> None:
    assert policy.version


def test_implementations_satisfy_budget_contracts() -> None:
    estimator = Utf8ByteTokenEstimator()
    policy = DeterministicContextBudgetPolicy(
        estimator=estimator,
    )

    assert_token_estimator_contract(estimator)
    assert_budget_policy_contract(policy)


def test_utf8_estimator_is_deterministic() -> None:
    estimator = Utf8ByteTokenEstimator(
        bytes_per_token=4,
    )

    assert estimator.estimate("abcdefgh") == 2
    assert estimator.estimate("é") == 1
    assert estimator.estimate("") == 0
    assert estimator.estimate("abcdefgh") == 2


def test_utf8_estimator_requires_positive_bytes_per_token() -> None:
    with pytest.raises(
        ValueError,
        match="bytes_per_token must be greater than 0",
    ):
        Utf8ByteTokenEstimator(
            bytes_per_token=0,
        )


def test_budget_reserves_base_input_and_output_capacity() -> None:
    budget = ContextBudget(
        max_total_tokens=100,
        base_input_tokens=25,
        reserved_output_tokens=30,
    )

    assert budget.available_context_tokens == 45


def test_budget_rejects_overcommitted_capacity() -> None:
    with pytest.raises(
        ValidationError,
        match="must not exceed max_total_tokens",
    ):
        ContextBudget(
            max_total_tokens=10,
            base_input_tokens=6,
            reserved_output_tokens=5,
        )


def test_no_pressure_preserves_complete_bundle() -> None:
    bundle = make_bundle()
    policy = DeterministicContextBudgetPolicy(
        estimator=Utf8ByteTokenEstimator(
            bytes_per_token=4,
        )
    )

    result = policy.apply(
        bundle,
        ContextBudget(
            max_total_tokens=10,
        ),
    )

    assert result.bundle == bundle
    assert result.estimated_tokens == 4
    assert result.budget_tokens == 10
    assert result.dropped_item_ids == ()


def test_budget_pressure_retains_canonical_prefix() -> None:
    bundle = make_bundle()
    policy = DeterministicContextBudgetPolicy(
        estimator=Utf8ByteTokenEstimator(
            bytes_per_token=4,
        )
    )

    result = policy.apply(
        bundle,
        ContextBudget(
            max_total_tokens=2,
        ),
    )

    assert [item.item_id for section in result.bundle.sections for item in section.items] == [
        "shared:1",
    ]
    assert result.estimated_tokens == 1
    assert result.budget_tokens == 2
    assert result.dropped_item_ids == (
        "delivery:1",
        "subject:1",
    )


def test_reserved_output_reduces_retained_context() -> None:
    bundle = make_bundle()
    policy = DeterministicContextBudgetPolicy(
        estimator=Utf8ByteTokenEstimator(
            bytes_per_token=4,
        )
    )

    result = policy.apply(
        bundle,
        ContextBudget(
            max_total_tokens=6,
            base_input_tokens=1,
            reserved_output_tokens=3,
        ),
    )

    assert [item.item_id for section in result.bundle.sections for item in section.items] == [
        "shared:1",
    ]
    assert result.budget_tokens == 2
    assert result.dropped_item_ids == (
        "delivery:1",
        "subject:1",
    )


def test_zero_context_capacity_drops_all_items() -> None:
    bundle = make_bundle()
    policy = DeterministicContextBudgetPolicy(estimator=Utf8ByteTokenEstimator())

    result = policy.apply(
        bundle,
        ContextBudget(
            max_total_tokens=10,
            base_input_tokens=4,
            reserved_output_tokens=6,
        ),
    )

    assert result.bundle.sections == ()
    assert result.estimated_tokens == 0
    assert result.budget_tokens == 0
    assert result.dropped_item_ids == (
        "shared:1",
        "delivery:1",
        "subject:1",
    )


def test_budgeting_is_deterministic_for_fixed_input() -> None:
    bundle = make_bundle()
    policy = DeterministicContextBudgetPolicy(estimator=Utf8ByteTokenEstimator())
    budget = ContextBudget(
        max_total_tokens=3,
    )

    first = policy.apply(bundle, budget)
    second = policy.apply(bundle, budget)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


class NegativeEstimator:
    @property
    def version(self) -> str:
        return "broken"

    def estimate(
        self,
        text: str,
    ) -> int:
        return -1


def test_negative_estimator_result_fails_closed() -> None:
    policy = DeterministicContextBudgetPolicy(
        estimator=NegativeEstimator(),
    )

    with pytest.raises(
        ValueError,
        match="negative estimate",
    ):
        policy.apply(
            make_bundle(),
            ContextBudget(
                max_total_tokens=10,
            ),
        )
