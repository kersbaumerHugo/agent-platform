import pytest

from agent_platform.application.context_assembler import (
    DeterministicContextAssembler,
)
from agent_platform.contracts.context import ContextAssemblerContract
from agent_platform.domain.context import (
    ContextBundle,
    ContextContribution,
    ContextItem,
    ContextProvenance,
    ContextRef,
    ContextRole,
    content_sha256,
)


def make_context(
    *,
    role: ContextRole = ContextRole.SUBJECT,
    namespace: str = "project:homelab",
) -> ContextRef:
    return ContextRef(
        role=role,
        namespace=namespace,
    )


def make_item(
    *,
    item_id: str,
    context: ContextRef,
    provider: str,
    source_id: str,
    content: str,
    kind: str = "fact",
) -> ContextItem:
    return ContextItem(
        item_id=item_id,
        content=content,
        kind=kind,
        context=context,
        provenance=ContextProvenance(
            provider=provider,
            source_id=source_id,
            content_hash=content_sha256(content),
        ),
    )


def make_contribution(
    *,
    provider: str,
    context: ContextRef,
    items: tuple[ContextItem, ...],
) -> ContextContribution:
    return ContextContribution(
        provider=provider,
        context=context,
        items=items,
    )


def assert_assembler_contract(
    assembler: ContextAssemblerContract,
) -> None:
    assert assembler.version


def test_assembler_satisfies_contract() -> None:
    assert_assembler_contract(DeterministicContextAssembler())


def test_empty_input_produces_empty_bundle() -> None:
    assembler = DeterministicContextAssembler()

    assert assembler.assemble([]) == ContextBundle()


def test_empty_contributions_do_not_create_sections() -> None:
    assembler = DeterministicContextAssembler()
    context = make_context()

    bundle = assembler.assemble(
        [
            ContextContribution(
                provider="memory",
                context=context,
            )
        ]
    )

    assert bundle.sections == ()


def test_contributions_for_same_context_merge_into_one_section() -> None:
    assembler = DeterministicContextAssembler()
    context = make_context()
    memory_item = make_item(
        item_id="memory:1",
        context=context,
        provider="memory",
        source_id="1",
        content="memory context",
    )
    workspace_item = make_item(
        item_id="workspace:1",
        context=context,
        provider="workspace",
        source_id="docs/context.md",
        content="workspace context",
    )

    bundle = assembler.assemble(
        [
            make_contribution(
                provider="workspace",
                context=context,
                items=(workspace_item,),
            ),
            make_contribution(
                provider="memory",
                context=context,
                items=(memory_item,),
            ),
        ]
    )

    assert len(bundle.sections) == 1
    assert bundle.sections[0].context == context
    assert [item.item_id for item in bundle.sections[0].items] == [
        "memory:1",
        "workspace:1",
    ]


def test_section_order_is_canonical() -> None:
    assembler = DeterministicContextAssembler()
    shared = make_context(
        role=ContextRole.SHARED,
        namespace="global",
    )
    delivery = make_context(
        role=ContextRole.DELIVERY,
        namespace="app:linkedin",
    )
    subject_b = make_context(
        role=ContextRole.SUBJECT,
        namespace="project:zeta",
    )
    subject_a = make_context(
        role=ContextRole.SUBJECT,
        namespace="project:alpha",
    )

    contributions = [
        make_contribution(
            provider="memory",
            context=subject_b,
            items=(
                make_item(
                    item_id="subject-b",
                    context=subject_b,
                    provider="memory",
                    source_id="subject-b",
                    content="subject b",
                ),
            ),
        ),
        make_contribution(
            provider="memory",
            context=delivery,
            items=(
                make_item(
                    item_id="delivery",
                    context=delivery,
                    provider="memory",
                    source_id="delivery",
                    content="delivery",
                ),
            ),
        ),
        make_contribution(
            provider="memory",
            context=subject_a,
            items=(
                make_item(
                    item_id="subject-a",
                    context=subject_a,
                    provider="memory",
                    source_id="subject-a",
                    content="subject a",
                ),
            ),
        ),
        make_contribution(
            provider="memory",
            context=shared,
            items=(
                make_item(
                    item_id="shared",
                    context=shared,
                    provider="memory",
                    source_id="shared",
                    content="shared",
                ),
            ),
        ),
    ]

    bundle = assembler.assemble(contributions)

    assert [
        (
            section.context.role,
            section.context.namespace,
        )
        for section in bundle.sections
    ] == [
        (ContextRole.SHARED, "global"),
        (ContextRole.DELIVERY, "app:linkedin"),
        (ContextRole.SUBJECT, "project:alpha"),
        (ContextRole.SUBJECT, "project:zeta"),
    ]


def test_provider_input_order_does_not_change_bundle() -> None:
    assembler = DeterministicContextAssembler()
    context = make_context()
    memory = make_contribution(
        provider="memory",
        context=context,
        items=(
            make_item(
                item_id="memory:1",
                context=context,
                provider="memory",
                source_id="1",
                content="memory context",
            ),
        ),
    )
    workspace = make_contribution(
        provider="workspace",
        context=context,
        items=(
            make_item(
                item_id="workspace:1",
                context=context,
                provider="workspace",
                source_id="docs/context.md",
                content="workspace context",
            ),
        ),
    )

    first = assembler.assemble([memory, workspace])
    second = assembler.assemble([workspace, memory])

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_item_order_inside_contribution_is_preserved() -> None:
    assembler = DeterministicContextAssembler()
    context = make_context()
    first = make_item(
        item_id="memory:first",
        context=context,
        provider="memory",
        source_id="first",
        content="more relevant",
    )
    second = make_item(
        item_id="memory:second",
        context=context,
        provider="memory",
        source_id="second",
        content="less relevant",
    )

    bundle = assembler.assemble(
        [
            make_contribution(
                provider="memory",
                context=context,
                items=(first, second),
            )
        ]
    )

    assert bundle.sections[0].items == (
        first,
        second,
    )


def test_exact_duplicate_item_is_deduplicated() -> None:
    assembler = DeterministicContextAssembler()
    context = make_context()
    item = make_item(
        item_id="memory:1",
        context=context,
        provider="memory",
        source_id="1",
        content="same context",
    )

    bundle = assembler.assemble(
        [
            make_contribution(
                provider="memory",
                context=context,
                items=(item,),
            ),
            make_contribution(
                provider="memory",
                context=context,
                items=(item,),
            ),
        ]
    )

    assert bundle.sections[0].items == (item,)


def test_conflicting_same_item_id_fails_closed() -> None:
    assembler = DeterministicContextAssembler()
    context = make_context()
    first = make_item(
        item_id="memory:1",
        context=context,
        provider="memory",
        source_id="1",
        content="original context",
    )
    conflicting = make_item(
        item_id="memory:1",
        context=context,
        provider="memory",
        source_id="1",
        content="different context",
    )

    with pytest.raises(
        ValueError,
        match="conflicting items",
    ):
        assembler.assemble(
            [
                make_contribution(
                    provider="memory",
                    context=context,
                    items=(first,),
                ),
                make_contribution(
                    provider="memory",
                    context=context,
                    items=(conflicting,),
                ),
            ]
        )
