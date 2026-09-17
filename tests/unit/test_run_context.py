from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest

from agent_platform.application.run_context import (
    InMemoryRunContextBindings,
)
from agent_platform.domain.context import content_sha256
from agent_platform.domain.context_preparation import (
    ContextPreparationResult,
)
from agent_platform.domain.context_rendering import RenderedContext
from agent_platform.domain.context_trace import (
    ContextBudgetTrace,
    ContextInjectionTrace,
    ContextPreparationTrace,
    ContextRenderingTrace,
)


def make_prepared(
    text: str,
) -> ContextPreparationResult:
    content_hash = content_sha256(text)
    rendered = RenderedContext(
        renderer="markdown",
        version="v0",
        text=text,
        content_hash=content_hash,
    )
    trace = ContextPreparationTrace(
        version="v0",
        planner="deterministic",
        planner_version="v0",
        provider_traces=(),
        assembler_version="v0",
        budget=ContextBudgetTrace(
            policy_version="canonical-prefix-v0",
            estimator_version="utf8-bytes-v0",
            budget_tokens=128,
            estimated_tokens=1 if text else 0,
            dropped_item_ids=(),
        ),
        rendering=ContextRenderingTrace(
            renderer=rendered.renderer,
            version=rendered.version,
            content_hash=rendered.content_hash,
        ),
        injection=ContextInjectionTrace(
            injector="reference-message",
            version="v0",
        ),
    )
    return ContextPreparationResult(
        rendered=rendered,
        trace=trace,
    )


def test_bind_and_resolve_by_exact_run_id() -> None:
    bindings = InMemoryRunContextBindings()
    run_id = UUID("11111111-1111-1111-1111-111111111111")
    prepared = make_prepared("context-a")

    bindings.bind(run_id, prepared)

    assert bindings.resolve(run_id) == prepared
    assert bindings.resolve(UUID("22222222-2222-2222-2222-222222222222")) is None


def test_same_binding_is_idempotent() -> None:
    bindings = InMemoryRunContextBindings()
    run_id = UUID("11111111-1111-1111-1111-111111111111")
    prepared = make_prepared("context-a")

    bindings.bind(run_id, prepared)
    bindings.bind(run_id, prepared)

    assert bindings.resolve(run_id) == prepared


def test_conflicting_duplicate_binding_fails_closed() -> None:
    bindings = InMemoryRunContextBindings()
    run_id = UUID("11111111-1111-1111-1111-111111111111")

    bindings.bind(run_id, make_prepared("context-a"))

    with pytest.raises(
        ValueError,
        match="already exists with different prepared context",
    ):
        bindings.bind(run_id, make_prepared("context-b"))

    assert bindings.resolve(run_id) == make_prepared("context-a")


def test_release_is_idempotent() -> None:
    bindings = InMemoryRunContextBindings()
    run_id = UUID("11111111-1111-1111-1111-111111111111")

    bindings.bind(run_id, make_prepared("context-a"))
    bindings.release(run_id)
    bindings.release(run_id)

    assert bindings.resolve(run_id) is None


def test_two_run_ids_remain_isolated() -> None:
    bindings = InMemoryRunContextBindings()
    run_a = UUID("11111111-1111-1111-1111-111111111111")
    run_b = UUID("22222222-2222-2222-2222-222222222222")
    prepared_a = make_prepared("context-a")
    prepared_b = make_prepared("context-b")

    bindings.bind(run_a, prepared_a)
    bindings.bind(run_b, prepared_b)

    assert bindings.resolve(run_a) == prepared_a
    assert bindings.resolve(run_b) == prepared_b


def test_concurrent_bind_and_resolve_preserves_isolation() -> None:
    bindings = InMemoryRunContextBindings()
    barrier = Barrier(2)

    cases = (
        (
            UUID("11111111-1111-1111-1111-111111111111"),
            make_prepared("context-a"),
        ),
        (
            UUID("22222222-2222-2222-2222-222222222222"),
            make_prepared("context-b"),
        ),
    )

    def bind_and_resolve(
        case: tuple[UUID, ContextPreparationResult],
    ) -> ContextPreparationResult | None:
        run_id, prepared = case
        barrier.wait()
        bindings.bind(run_id, prepared)
        barrier.wait()
        return bindings.resolve(run_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(bind_and_resolve, cases))

    assert results == tuple(prepared for _, prepared in cases)
    assert bindings.resolve(cases[0][0]) == cases[0][1]
    assert bindings.resolve(cases[1][0]) == cases[1][1]
