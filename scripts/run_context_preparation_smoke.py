import argparse
import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from agent_platform.adapters.memory.context_provider import (
    MemoryContextProvider,
)
from agent_platform.adapters.memory.sqlite import (
    SQLiteFTSRetrieval,
    SQLiteMemoryStore,
)
from agent_platform.application.context_assembler import (
    DeterministicContextAssembler,
)
from agent_platform.application.context_budget import (
    DeterministicContextBudgetPolicy,
    Utf8ByteTokenEstimator,
)
from agent_platform.application.context_injector import (
    ReferenceMessageInjector,
)
from agent_platform.application.context_renderer import (
    MarkdownContextRenderer,
)
from agent_platform.application.context_trace import ContextTraceBuilder
from agent_platform.application.recall_planner import (
    DeterministicRecallPlanner,
)
from agent_platform.application.retrieval_acceptance import (
    LexicalRetrievalAcceptanceGate,
)
from agent_platform.domain.context import (
    ContextBundle,
    ContextRef,
    ContextRole,
    content_sha256,
)
from agent_platform.domain.context_budget import (
    BudgetedContextBundle,
    ContextBudget,
)
from agent_platform.domain.context_preparation import RecallIntent, RecallPlan
from agent_platform.domain.context_rendering import RenderedContext
from agent_platform.domain.context_trace import ContextPreparationTrace
from agent_platform.domain.memory import MemoryRecord, MemoryScope
from agent_platform.domain.model import (
    MessageRole,
    ModelMessage,
    ModelRequest,
)
from agent_platform.domain.work import WorkRequest, WorkStep


class SmokeSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    recall_plan: RecallPlan
    accepted_source_ids: tuple[str, ...]
    accepted_source_hashes: tuple[str, ...]
    context_bundle: ContextBundle
    budgeted_bundle: BudgetedContextBundle
    rendered: RenderedContext
    injected_request: ModelRequest
    trace: ContextPreparationTrace


class SmokeChecks(BaseModel):
    model_config = ConfigDict(frozen=True)

    recall_plan: bool
    accepted_source_ids: bool
    accepted_source_hashes: bool
    context_bundle: bool
    budgeted_bundle: bool
    rendered_bytes: bool
    rendered_context_hash: bool
    injected_message_shape: bool
    trace: bool

    @property
    def all_match(self) -> bool:
        return all(
            (
                self.recall_plan,
                self.accepted_source_ids,
                self.accepted_source_hashes,
                self.context_bundle,
                self.budgeted_bundle,
                self.rendered_bytes,
                self.rendered_context_hash,
                self.injected_message_shape,
                self.trace,
            )
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Run the deterministic M10 end-to-end context preparation smoke.")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evidence/artifacts/m10-context-preparation-smoke-v0.json"),
    )
    return parser.parse_args()


def fixed_work() -> WorkRequest:
    return WorkRequest(
        objective="Write a LinkedIn post about the homelab.",
        contexts=[
            ContextRef(
                role=ContextRole.SHARED,
                namespace="global",
            ),
            ContextRef(
                role=ContextRole.DELIVERY,
                namespace="app:linkedin",
            ),
            ContextRef(
                role=ContextRole.SUBJECT,
                namespace="project:homelab",
            ),
        ],
        steps=[
            WorkStep(
                step_id="draft",
                agent_id="writer",
                input="Draft the post.",
            ),
        ],
    )


def fixed_memories() -> tuple[MemoryRecord, ...]:
    common = "Write a LinkedIn post about the homelab. Draft the post. "

    return (
        MemoryRecord(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            scope=MemoryScope(namespace="global"),
            content=(common + "Shared preference: use concise language."),
            created_at=datetime(
                2026,
                9,
                16,
                12,
                0,
                0,
                tzinfo=UTC,
            ),
            metadata={"kind": "preference"},
        ),
        MemoryRecord(
            id=UUID("22222222-2222-2222-2222-222222222222"),
            scope=MemoryScope(namespace="app:linkedin"),
            content=(common + "Delivery style: keep the LinkedIn post professional."),
            created_at=datetime(
                2026,
                9,
                16,
                12,
                0,
                1,
                tzinfo=UTC,
            ),
            metadata={"kind": "style"},
        ),
        MemoryRecord(
            id=UUID("33333333-3333-3333-3333-333333333333"),
            scope=MemoryScope(namespace="project:homelab"),
            content=(
                common + "Subject fact: Prometheus collects metrics and Grafana visualizes them."
            ),
            created_at=datetime(
                2026,
                9,
                16,
                12,
                0,
                2,
                tzinfo=UTC,
            ),
            metadata={"kind": "fact"},
        ),
    )


async def execute_once(
    database_path: Path,
) -> SmokeSnapshot:
    work = fixed_work()
    step = work.steps[0]

    store = SQLiteMemoryStore(database_path)
    retrieval = SQLiteFTSRetrieval(database_path)
    acceptance = LexicalRetrievalAcceptanceGate()
    provider = MemoryContextProvider(
        retrieval=retrieval,
        acceptance=acceptance,
    )

    for memory in fixed_memories():
        await store.store(memory)

    planner = DeterministicRecallPlanner()
    assembler = DeterministicContextAssembler()
    estimator = Utf8ByteTokenEstimator()
    budget_policy = DeterministicContextBudgetPolicy(
        estimator=estimator,
    )
    renderer = MarkdownContextRenderer()
    injector = ReferenceMessageInjector()
    trace_builder = ContextTraceBuilder()

    plan = await planner.plan(
        RecallIntent(
            objective=work.objective,
            step_input=step.input,
            contexts=tuple(work.contexts),
        )
    )

    provider_results = [await provider.provide(request) for request in plan.requests]

    accepted_source_ids = tuple(
        source.source_id for result in provider_results for source in result.trace.accepted_sources
    )
    accepted_source_hashes = tuple(
        source.content_hash
        for result in provider_results
        for source in result.trace.accepted_sources
    )

    bundle = assembler.assemble(tuple(result.contribution for result in provider_results))

    budgeted = budget_policy.apply(
        bundle,
        ContextBudget(
            max_total_tokens=512,
            reserved_output_tokens=128,
        ),
    )

    rendered = renderer.render(budgeted)

    base_request = ModelRequest(
        run_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        messages=[
            ModelMessage(
                role=MessageRole.SYSTEM,
                content="You are a writing assistant.",
            ),
            ModelMessage(
                role=MessageRole.USER,
                content=step.input,
            ),
        ],
        max_tokens=128,
    )
    injected = injector.inject(
        base_request,
        rendered,
    )

    trace = trace_builder.build(
        plan=plan,
        provider_results=provider_results,
        assembler_version=assembler.version,
        budget_policy_version=budget_policy.version,
        token_estimator_version=estimator.version,
        budgeted=budgeted,
        rendered=rendered,
        injector_name=injector.name,
        injector_version=injector.version,
    )

    return SmokeSnapshot(
        recall_plan=plan,
        accepted_source_ids=accepted_source_ids,
        accepted_source_hashes=accepted_source_hashes,
        context_bundle=bundle,
        budgeted_bundle=budgeted,
        rendered=rendered,
        injected_request=injected,
        trace=trace,
    )


def compare_snapshots(
    first: SmokeSnapshot,
    second: SmokeSnapshot,
) -> SmokeChecks:
    return SmokeChecks(
        recall_plan=(first.recall_plan == second.recall_plan),
        accepted_source_ids=(first.accepted_source_ids == second.accepted_source_ids),
        accepted_source_hashes=(first.accepted_source_hashes == second.accepted_source_hashes),
        context_bundle=(first.context_bundle == second.context_bundle),
        budgeted_bundle=(first.budgeted_bundle == second.budgeted_bundle),
        rendered_bytes=(
            first.rendered.text.encode("utf-8") == second.rendered.text.encode("utf-8")
        ),
        rendered_context_hash=(first.rendered.content_hash == second.rendered.content_hash),
        injected_message_shape=(first.injected_request == second.injected_request),
        trace=(first.trace == second.trace),
    )


def plan_evidence(
    plan: RecallPlan,
) -> dict[str, object]:
    return {
        "planner": plan.planner,
        "version": plan.version,
        "requests": [
            {
                "request_id": request.request_id,
                "context": request.context.model_dump(mode="json"),
                "query_hash": content_sha256(request.query),
                "limit": request.limit,
            }
            for request in plan.requests
        ],
    }


def bundle_evidence(
    bundle: ContextBundle,
) -> list[dict[str, object]]:
    return [
        {
            "context": section.context.model_dump(mode="json"),
            "items": [
                {
                    "item_id": item.item_id,
                    "kind": item.kind,
                    "provider": (item.provenance.provider),
                    "source_id": (item.provenance.source_id),
                    "content_hash": (item.provenance.content_hash),
                }
                for item in section.items
            ],
        }
        for section in bundle.sections
    ]


def injected_shape(
    request: ModelRequest,
) -> dict[str, object]:
    return {
        "run_id": str(request.run_id),
        "message_count": len(request.messages),
        "messages": [
            {
                "role": message.role.value,
                "content_hash": content_sha256(message.content or ""),
                "tool_call_count": len(message.tool_calls),
                "has_tool_call_id": (message.tool_call_id is not None),
            }
            for message in request.messages
        ],
        "tool_count": len(request.tools),
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
    }


def build_report(
    snapshot: SmokeSnapshot,
    checks: SmokeChecks,
) -> dict[str, object]:
    work = fixed_work()

    return {
        "suite_id": ("m10-context-preparation-smoke-v0"),
        "scenario": {
            "work": {
                "objective": work.objective,
                "contexts": [context.model_dump(mode="json") for context in work.contexts],
                "steps": [step.model_dump(mode="json") for step in work.steps],
            }
        },
        "checks": checks.model_dump(),
        "deterministic_reproducibility": (checks.all_match),
        "evidence": {
            "recall_plan": plan_evidence(snapshot.recall_plan),
            "accepted_source_ids": list(snapshot.accepted_source_ids),
            "accepted_source_hashes": list(snapshot.accepted_source_hashes),
            "context_bundle": bundle_evidence(snapshot.context_bundle),
            "budget": {
                "budget_tokens": (snapshot.budgeted_bundle.budget_tokens),
                "estimated_tokens": (snapshot.budgeted_bundle.estimated_tokens),
                "dropped_item_ids": list(snapshot.budgeted_bundle.dropped_item_ids),
            },
            "rendered_context": {
                "renderer": snapshot.rendered.renderer,
                "version": snapshot.rendered.version,
                "content_hash": (snapshot.rendered.content_hash),
                "utf8_byte_length": len(snapshot.rendered.text.encode("utf-8")),
            },
            "injected_request_shape": (injected_shape(snapshot.injected_request)),
            "trace": snapshot.trace.model_dump(mode="json"),
        },
    }


async def main() -> None:
    args = parse_args()

    with tempfile.TemporaryDirectory(prefix="agent-platform-m10-smoke-first-") as first_temp_dir:
        first = await execute_once(Path(first_temp_dir) / "memory.sqlite3")

    with tempfile.TemporaryDirectory(prefix="agent-platform-m10-smoke-second-") as second_temp_dir:
        second = await execute_once(Path(second_temp_dir) / "memory.sqlite3")

    checks = compare_snapshots(
        first,
        second,
    )
    report = build_report(
        first,
        checks,
    )

    serialized = json.dumps(
        report,
        indent=2,
        sort_keys=True,
    )
    print(serialized)

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.output.write_text(
        serialized + "\n",
        encoding="utf-8",
    )

    if not checks.all_match:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
