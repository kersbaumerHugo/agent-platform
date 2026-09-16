import json

import pytest

from agent_platform.domain.context import ContextRole
from agent_platform.domain.model import MessageRole
from scripts.run_context_preparation_smoke import (
    build_report,
    compare_snapshots,
    execute_once,
)


@pytest.mark.asyncio
async def test_fixed_smoke_is_deterministic_across_independent_stores(
    tmp_path,
) -> None:
    first = await execute_once(
        tmp_path / "first.sqlite3",
    )
    second = await execute_once(
        tmp_path / "second.sqlite3",
    )

    checks = compare_snapshots(
        first,
        second,
    )

    assert checks.all_match
    assert all(checks.model_dump().values())


@pytest.mark.asyncio
async def test_fixed_smoke_matches_linkedin_homelab_shape(
    tmp_path,
) -> None:
    snapshot = await execute_once(
        tmp_path / "memory.sqlite3",
    )

    assert [
        (
            request.context.role,
            request.context.namespace,
        )
        for request in snapshot.recall_plan.requests
    ] == [
        (
            ContextRole.SHARED,
            "global",
        ),
        (
            ContextRole.DELIVERY,
            "app:linkedin",
        ),
        (
            ContextRole.SUBJECT,
            "project:homelab",
        ),
    ]

    assert snapshot.accepted_source_ids == (
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
    )

    assert [
        (
            section.context.role,
            section.context.namespace,
        )
        for section in snapshot.context_bundle.sections
    ] == [
        (
            ContextRole.SHARED,
            "global",
        ),
        (
            ContextRole.DELIVERY,
            "app:linkedin",
        ),
        (
            ContextRole.SUBJECT,
            "project:homelab",
        ),
    ]

    assert snapshot.budgeted_bundle.dropped_item_ids == ()
    assert snapshot.rendered.text
    assert snapshot.trace.rendering.content_hash == snapshot.rendered.content_hash

    assert [message.role for message in snapshot.injected_request.messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.USER,
    ]


@pytest.mark.asyncio
async def test_smoke_report_keeps_raw_context_out_of_evidence(
    tmp_path,
) -> None:
    snapshot = await execute_once(
        tmp_path / "memory.sqlite3",
    )
    checks = compare_snapshots(
        snapshot,
        snapshot.model_copy(deep=True),
    )
    report = build_report(
        snapshot,
        checks,
    )

    serialized = json.dumps(
        report,
        sort_keys=True,
    )

    assert "Shared preference: use concise language." not in serialized
    assert "Delivery style: keep the LinkedIn post professional." not in serialized
    assert "Subject fact: Prometheus collects metrics" not in serialized
    assert snapshot.rendered.content_hash in serialized
    assert "11111111-1111-1111-1111-111111111111" in serialized
