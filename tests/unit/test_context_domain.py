import pytest
from pydantic import ValidationError

from agent_platform.domain.context import (
    ContextBundle,
    ContextContribution,
    ContextItem,
    ContextProvenance,
    ContextRef,
    ContextRole,
    ContextSection,
    content_sha256,
)


def make_context(
    *,
    role: ContextRole = ContextRole.SUBJECT,
    namespace: str = "project:homelab",
) -> ContextRef:
    return ContextRef(role=role, namespace=namespace)


def make_item(
    *,
    item_id: str = "item-1",
    content: str = "Prometheus and Grafana are the observability baseline.",
    kind: str = "decision",
    context: ContextRef | None = None,
    provider: str = "memory",
    source_id: str = "memory-1",
    source_revision: str | None = None,
) -> ContextItem:
    resolved_context = context or make_context()
    return ContextItem(
        item_id=item_id,
        content=content,
        kind=kind,
        context=resolved_context,
        provenance=ContextProvenance(
            provider=provider,
            source_id=source_id,
            source_revision=source_revision,
            content_hash=content_sha256(content),
        ),
    )


def test_content_hash_is_deterministic() -> None:
    content = "same context content"
    first = content_sha256(content)
    second = content_sha256(content)

    assert first == second
    assert first.startswith("sha256:")
    assert len(first) == len("sha256:") + 64


def test_content_hash_changes_when_content_changes() -> None:
    assert content_sha256("alpha") != content_sha256("beta")


def test_context_item_is_source_neutral() -> None:
    context = make_context()
    item = make_item(
        context=context,
        provider="workspace",
        source_id="docs/architecture.md",
        source_revision="abc123",
    )

    assert item.context == context
    assert item.kind == "decision"
    assert item.provenance.provider == "workspace"
    assert item.provenance.source_id == "docs/architecture.md"
    assert item.provenance.source_revision == "abc123"


def test_context_item_rejects_mismatched_content_hash() -> None:
    with pytest.raises(
        ValidationError,
        match="content_hash must match item content",
    ):
        ContextItem(
            item_id="item-1",
            content="actual content",
            kind="fact",
            context=make_context(),
            provenance=ContextProvenance(
                provider="memory",
                source_id="memory-1",
                content_hash=content_sha256("different content"),
            ),
        )


def test_context_contribution_normalizes_provider_output() -> None:
    context = make_context()
    items = (
        make_item(item_id="one", context=context, source_id="memory-1"),
        make_item(
            item_id="two",
            content="Git is the configuration source of truth.",
            context=context,
            source_id="memory-2",
        ),
    )

    contribution = ContextContribution(
        provider="memory",
        context=context,
        items=items,
    )

    assert contribution.provider == "memory"
    assert contribution.context == context
    assert contribution.items == items


def test_context_contribution_rejects_cross_context_item() -> None:
    with pytest.raises(
        ValidationError,
        match="share the contribution context",
    ):
        ContextContribution(
            provider="memory",
            context=make_context(namespace="project:homelab"),
            items=(
                make_item(
                    context=make_context(namespace="project:agent-platform"),
                ),
            ),
        )


def test_context_contribution_rejects_cross_provider_item() -> None:
    context = make_context()

    with pytest.raises(
        ValidationError,
        match="share the contribution provider",
    ):
        ContextContribution(
            provider="memory",
            context=context,
            items=(make_item(context=context, provider="workspace"),),
        )


def test_context_section_can_combine_multiple_providers() -> None:
    context = make_context()
    section = ContextSection(
        context=context,
        items=(
            make_item(
                item_id="memory-item",
                context=context,
                provider="memory",
                source_id="memory-1",
            ),
            make_item(
                item_id="workspace-item",
                content="The current architecture diagram documents Proxmox.",
                kind="fact",
                context=context,
                provider="workspace",
                source_id="docs/architecture.md",
            ),
        ),
    )

    assert [item.provenance.provider for item in section.items] == [
        "memory",
        "workspace",
    ]


def test_context_section_rejects_cross_context_item() -> None:
    with pytest.raises(
        ValidationError,
        match="share the section context",
    ):
        ContextSection(
            context=make_context(
                role=ContextRole.SHARED,
                namespace="global",
            ),
            items=(make_item(context=make_context()),),
        )


def test_context_bundle_preserves_context_roles_and_provenance() -> None:
    shared = make_context(role=ContextRole.SHARED, namespace="global")
    delivery = make_context(
        role=ContextRole.DELIVERY,
        namespace="app:linkedin",
    )
    subject = make_context(
        role=ContextRole.SUBJECT,
        namespace="project:homelab",
    )

    bundle = ContextBundle(
        sections=(
            ContextSection(
                context=shared,
                items=(
                    make_item(
                        item_id="shared-1",
                        content="Prefer concise technical explanations.",
                        kind="preference",
                        context=shared,
                        source_id="memory-global-1",
                    ),
                ),
            ),
            ContextSection(
                context=delivery,
                items=(
                    make_item(
                        item_id="delivery-1",
                        content="Use short paragraphs and natural language.",
                        kind="style",
                        context=delivery,
                        source_id="memory-linkedin-1",
                    ),
                ),
            ),
            ContextSection(
                context=subject,
                items=(
                    make_item(
                        item_id="subject-1",
                        context=subject,
                        source_id="memory-homelab-1",
                    ),
                ),
            ),
        ),
    )

    assert [section.context for section in bundle.sections] == [
        shared,
        delivery,
        subject,
    ]
    assert bundle.sections[2].items[0].provenance.provider == "memory"


def test_context_bundle_rejects_duplicate_context_sections() -> None:
    context = make_context()

    with pytest.raises(
        ValidationError,
        match="unique by role and namespace",
    ):
        ContextBundle(
            sections=(
                ContextSection(context=context),
                ContextSection(context=context),
            ),
        )


def test_context_bundle_can_be_empty() -> None:
    assert ContextBundle().sections == ()


def test_context_ir_serialization_is_stable_for_fixed_input() -> None:
    context = make_context()
    bundle = ContextBundle(
        sections=(
            ContextSection(
                context=context,
                items=(make_item(context=context),),
            ),
        ),
    )

    first = bundle.model_dump_json()
    second = bundle.model_dump_json()

    assert first == second
