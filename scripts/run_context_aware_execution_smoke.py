import argparse
import asyncio
import json
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

from agent_platform.adapters.memory.context_provider import (
    MemoryContextProvider,
)
from agent_platform.adapters.memory.sqlite import (
    SQLiteFTSRetrieval,
    SQLiteMemoryStore,
)
from agent_platform.api.openai_compat import inject_bound_context
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
from agent_platform.application.context_preparation import PrepareContext
from agent_platform.application.context_renderer import (
    MarkdownContextRenderer,
)
from agent_platform.application.context_trace import ContextTraceBuilder
from agent_platform.application.model_gateway import ModelGateway
from agent_platform.application.recall_planner import (
    DeterministicRecallPlanner,
)
from agent_platform.application.retrieval_acceptance import (
    LexicalRetrievalAcceptanceGate,
)
from agent_platform.application.run_agent import RunAgent
from agent_platform.application.run_context import (
    InMemoryRunContextBindings,
)
from agent_platform.application.work_orchestrator import WorkOrchestrator
from agent_platform.domain.context import ContextRef, ContextRole, content_sha256
from agent_platform.domain.context_budget import ContextBudget
from agent_platform.domain.memory import MemoryRecord, MemoryScope
from agent_platform.domain.model import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelResult,
)
from agent_platform.domain.models import RuntimeRequest, RuntimeResult
from agent_platform.domain.observability import ObservationEvent
from agent_platform.domain.work import WorkRequest, WorkStep

RAW_CONTEXT_MARKER = "M11_PRIVATE_REFERENCE_MARKER"
_FIXED_TIME = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


class NoopObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


class DeterministicSmokeModel:
    @property
    def provider(self) -> str:
        return "m11-smoke"

    @property
    def model(self) -> str:
        return "deterministic-v0"

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        canonical_messages = [
            {
                "role": message.role.value,
                "content": message.content,
                "tool_call_id": message.tool_call_id,
                "tool_calls": [call.model_dump(mode="json") for call in message.tool_calls],
            }
            for message in request.messages
        ]
        payload = json.dumps(
            canonical_messages,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = sha256(payload.encode("utf-8")).hexdigest()

        return ModelResult(
            provider=self.provider,
            model=self.model,
            output=f"sha256:{digest}",
            finish_reason="stop",
        )


class GatewaySmokeRuntime:
    def __init__(
        self,
        *,
        bindings: InMemoryRunContextBindings,
        gateway: ModelGateway,
    ) -> None:
        self._bindings = bindings
        self._gateway = gateway
        self._injector = ReferenceMessageInjector()
        self.observations: list[dict[str, Any]] = []
        self.run_ids: list[UUID] = []

    @property
    def name(self) -> str:
        return "m11-gateway-smoke"

    async def execute(
        self,
        request: RuntimeRequest,
    ) -> RuntimeResult:
        prepared = self._bindings.resolve(request.run_id)
        required = self._bindings.is_required(request.run_id)

        base_request = ModelRequest(
            run_id=request.run_id,
            messages=[
                ModelMessage(
                    role=MessageRole.SYSTEM,
                    content="Platform system instruction.",
                ),
                ModelMessage(
                    role=MessageRole.USER,
                    content=request.input,
                ),
            ],
        )
        injected = inject_bound_context(
            base_request,
            self._bindings,
            self._injector,
        )

        context_message_count = (
            sum(message.content == prepared.rendered.text for message in injected.messages)
            if prepared is not None
            else 0
        )
        message_content_hashes = [
            (content_sha256(message.content) if message.content is not None else None)
            for message in injected.messages
        ]

        self.run_ids.append(request.run_id)
        self.observations.append(
            {
                "binding_present": prepared is not None,
                "binding_required": required,
                "rendered_context_hash": (
                    prepared.rendered.content_hash if prepared is not None else None
                ),
                "context_message_count": context_message_count,
                "message_roles": [message.role.value for message in injected.messages],
                "message_content_hashes": message_content_hashes,
                "system_message_unchanged": (
                    [
                        message.content
                        for message in injected.messages
                        if message.role is MessageRole.SYSTEM
                    ]
                    == ["Platform system instruction."]
                ),
            }
        )

        result = await self._gateway.generate(injected)
        return RuntimeResult(output=result.output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Run the deterministic M11 context-aware execution integration smoke twice.")
    )
    parser.add_argument(
        "--output",
        type=Path,
    )
    return parser.parse_args()


def _memories() -> tuple[MemoryRecord, ...]:
    shared_terms = f"homelab monitoring draft review {RAW_CONTEXT_MARKER}"

    return (
        MemoryRecord(
            id=UUID("11111111-1111-4111-8111-111111111111"),
            scope=MemoryScope(
                namespace="app:linkedin",
            ),
            content=(f"{shared_terms} linkedin delivery concise technical"),
            created_at=_FIXED_TIME,
            metadata={"kind": "delivery-guidance"},
        ),
        MemoryRecord(
            id=UUID("22222222-2222-4222-8222-222222222222"),
            scope=MemoryScope(
                namespace="project:homelab",
            ),
            content=(f"{shared_terms} architecture grafana prometheus"),
            created_at=_FIXED_TIME,
            metadata={"kind": "project-reference"},
        ),
    )


def _context_work() -> WorkRequest:
    return WorkRequest(
        objective="homelab monitoring",
        contexts=[
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
                input="draft",
            ),
            WorkStep(
                step_id="review",
                agent_id="reviewer",
                input="review",
            ),
        ],
    )


def _no_context_work() -> WorkRequest:
    return WorkRequest(
        objective="plain execution",
        steps=[
            WorkStep(
                step_id="execute",
                agent_id="worker",
                input="execute",
            )
        ],
    )


def _build_prepare_context(
    database_path: Path,
) -> PrepareContext:
    retrieval = SQLiteFTSRetrieval(database_path)
    acceptance = LexicalRetrievalAcceptanceGate()
    provider = MemoryContextProvider(
        retrieval=retrieval,
        acceptance=acceptance,
    )
    estimator = Utf8ByteTokenEstimator()

    return PrepareContext(
        planner=DeterministicRecallPlanner(),
        provider=provider,
        assembler=DeterministicContextAssembler(),
        budget_policy=DeterministicContextBudgetPolicy(
            estimator=estimator,
        ),
        token_estimator=estimator,
        renderer=MarkdownContextRenderer(),
        injector=ReferenceMessageInjector(),
        trace_builder=ContextTraceBuilder(),
    )


async def _seed_memory(
    database_path: Path,
) -> None:
    store = SQLiteMemoryStore(database_path)

    for memory in _memories():
        await store.store(memory)


def _normalize_work(
    *,
    result: Any,
    runtime: GatewaySmokeRuntime,
    bindings: InMemoryRunContextBindings,
) -> dict[str, Any]:
    normalized_steps = []

    for step_result in result.step_results:
        normalized_steps.append(
            {
                "step_id": step_result.step_id,
                "run_status": step_result.run.status.value,
                "output": step_result.run.output,
                "context_trace": (
                    step_result.context_trace.model_dump(mode="json")
                    if step_result.context_trace is not None
                    else None
                ),
            }
        )

    bindings_cleared = all(
        bindings.resolve(run_id) is None and not bindings.is_required(run_id)
        for run_id in runtime.run_ids
    )

    return {
        "status": result.status.value,
        "failed_step_id": result.failed_step_id,
        "contexts": [context.model_dump(mode="json") for context in result.contexts],
        "steps": normalized_steps,
        "runtime_observations": runtime.observations,
        "run_ids_distinct": (len(runtime.run_ids) == len(set(runtime.run_ids))),
        "bindings_cleared": bindings_cleared,
    }


async def execute_smoke(
    database_path: Path,
) -> dict[str, Any]:
    await _seed_memory(database_path)

    bindings = InMemoryRunContextBindings()
    gateway = ModelGateway(
        model=DeterministicSmokeModel(),
        observer=NoopObserver(),
    )
    runtime = GatewaySmokeRuntime(
        bindings=bindings,
        gateway=gateway,
    )
    run_agent = RunAgent(
        runtime=runtime,
        observer=NoopObserver(),
        run_context_bindings=bindings,
    )
    orchestrator = WorkOrchestrator(
        run_agent,
        prepare_context=_build_prepare_context(database_path),
        context_budget=ContextBudget(
            max_total_tokens=512,
            reserved_output_tokens=64,
        ),
    )

    context_result = await orchestrator.execute(_context_work())
    context_run_count = len(runtime.run_ids)

    no_context_result = await orchestrator.execute(_no_context_work())

    context_runtime_observations = runtime.observations[:context_run_count]
    no_context_runtime_observations = runtime.observations[context_run_count:]

    normalized = {
        "context_aware_work": _normalize_work(
            result=context_result,
            runtime=runtime,
            bindings=bindings,
        ),
        "no_context_work": {
            "status": no_context_result.status.value,
            "failed_step_id": no_context_result.failed_step_id,
            "contexts": [context.model_dump(mode="json") for context in no_context_result.contexts],
            "steps": [
                {
                    "step_id": step_result.step_id,
                    "run_status": step_result.run.status.value,
                    "output": step_result.run.output,
                    "context_trace": (
                        step_result.context_trace.model_dump(mode="json")
                        if step_result.context_trace is not None
                        else None
                    ),
                }
                for step_result in no_context_result.step_results
            ],
            "runtime_observations": (no_context_runtime_observations),
        },
        "context_runtime_observations": (context_runtime_observations),
        "total_runtime_calls": len(runtime.run_ids),
        "all_bindings_cleared": all(
            bindings.resolve(run_id) is None and not bindings.is_required(run_id)
            for run_id in runtime.run_ids
        ),
    }

    serialized = json.dumps(
        normalized,
        sort_keys=True,
    )
    normalized["raw_context_absent"] = RAW_CONTEXT_MARKER not in serialized

    return normalized


def _assert_smoke_invariants(
    report: dict[str, Any],
) -> None:
    context_work = report["context_aware_work"]
    no_context_work = report["no_context_work"]

    assert context_work["status"] == "succeeded"
    assert [step["step_id"] for step in context_work["steps"]] == ["draft", "review"]
    assert all(step["run_status"] == "succeeded" for step in context_work["steps"])
    assert all(step["context_trace"] is not None for step in context_work["steps"])

    context_observations = report["context_runtime_observations"]
    assert len(context_observations) == 2
    assert all(observation["binding_present"] for observation in context_observations)
    assert all(observation["binding_required"] for observation in context_observations)
    assert all(observation["context_message_count"] == 1 for observation in context_observations)
    assert all(
        observation["message_roles"] == ["system", "user", "user"]
        for observation in context_observations
    )
    assert all(observation["system_message_unchanged"] for observation in context_observations)

    assert no_context_work["status"] == "succeeded"
    assert len(no_context_work["runtime_observations"]) == 1
    no_context_observation = no_context_work["runtime_observations"][0]
    assert no_context_observation["binding_present"] is False
    assert no_context_observation["binding_required"] is False
    assert no_context_observation["context_message_count"] == 0
    assert no_context_observation["message_roles"] == [
        "system",
        "user",
    ]

    assert report["total_runtime_calls"] == 3
    assert report["all_bindings_cleared"] is True
    assert report["raw_context_absent"] is True


async def main() -> None:
    args = parse_args()

    with tempfile.TemporaryDirectory(prefix="agent-platform-m11-smoke-a-") as first_dir:
        first = await execute_smoke(Path(first_dir) / "memory.sqlite3")

    with tempfile.TemporaryDirectory(prefix="agent-platform-m11-smoke-b-") as second_dir:
        second = await execute_smoke(Path(second_dir) / "memory.sqlite3")

    _assert_smoke_invariants(first)
    _assert_smoke_invariants(second)

    deterministic = first == second

    report = {
        "suite_id": "m11-context-aware-execution-smoke-v0",
        "deterministic_reproducibility": deterministic,
        "invariants_passed": True,
        "run": first,
    }

    serialized_report = json.dumps(
        report,
        indent=2,
        sort_keys=True,
    )
    print(serialized_report)

    if args.output is not None:
        args.output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        args.output.write_text(
            serialized_report + "\n",
            encoding="utf-8",
        )

    if not deterministic:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
