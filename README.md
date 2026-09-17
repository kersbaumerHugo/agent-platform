# Agent Platform

A runtime-agnostic platform for executing, observing and evolving AI agents through explicit platform-owned contracts.

> Agent != Platform.

The platform is designed so runtimes, model providers and capability protocols remain replaceable.

## Current status

The platform currently includes:

- a replaceable runtime boundary;
- provider-neutral model execution;
- OpenRouter and local OpenAI-compatible model adapters;
- a local llama.cpp inference backend;
- platform-owned tool capabilities exposed through MCP;
- persistent Memory & Recall capabilities;
- lexical-first retrieval with SQLite FTS5/BM25;
- explicit retrieval ACCEPT / ABSTAIN policy;
- deterministic Work API and sequential orchestration;
- Eval-as-Code through a platform-owned Evaluation Plane;
- source-neutral Context IR and deterministic context preparation/injection;
- structured context preparation trace evidence;
- structured observability;
- persistent systemd-based deployment;
- a trusted self-development boundary;
- supervised autonomous Worker execution.

```text
Agent Runtime
    |
    v
RuntimeContract
    |
    +----> Model Gateway -> ModelContract
    |                         |
    |                         +----> OpenRouter
    |                         |
    |                         +----> Local OpenAI Adapter
    |                                  |
    |                                  v
    |                              llama-server
    |
    +----> MCP Adapter -> ToolRegistry
                              |
                              +----> ToolContract -> Tool
                              |
                              +----> memory_remember -> MemoryStoreContract -> SQLite
                              |
                              +----> memory_recall -> RetrievalContract
                                                       |
                                                       v
                                                FTS5 / BM25
                                                       |
                                                       v
                                             Acceptance Gate
                                              ACCEPT / ABSTAIN
```

## Validated agentic loop

```text
DSH
 -> Agent Platform Model Gateway
 -> selected ModelContract adapter
 -> tool_call
 -> DSH
 -> MCP
 -> Agent Platform ToolRegistry
 -> Tool
 -> DSH
 -> Model Gateway
 -> selected ModelContract adapter
 -> final response
```

## Validated context preparation pipeline

```text
Work / WorkStep
      |
      v
explicit ContextRef[]
      |
      v
DeterministicRecallPlanner
      |
      v
ContextProviderContract
      |
      v
MemoryContextProvider
      |
      v
ContextContribution[]
      |
      v
DeterministicContextAssembler
      |
      v
ContextBundle
      |
      v
DeterministicContextBudgetPolicy
      |
      v
BudgetedContextBundle
      |
      v
MarkdownContextRenderer
      |
      v
RenderedContext
      |
      v
ReferenceMessageInjector
      |
      v
ModelRequest
```

The M10 baseline keeps model-facing context separate from operational trace
evidence and never promotes retrieved context into a new system message by
structure.

## Implemented

- RuntimeContract
- DeepSeek Harness runtime adapter
- ModelContract
- OpenRouter model adapter
- local OpenAI-compatible model adapter
- local llama.cpp inference backend integration
- internal OpenAI-compatible Model Gateway
- ToolContract
- ToolRegistry
- MCP Streamable HTTP adapter
- diagnostic tool
- MemoryScope / MemoryRecord domain models
- MemoryStoreContract
- RetrievalContract
- RetrievalAcceptanceContract
- SQLite MemoryStore adapter
- SQLite FTS5/BM25 retrieval adapter
- deterministic Retrieval Acceptance Gate
- `memory_remember`
- `memory_recall`
- explicit scope isolation
- WorkRequest / WorkResult domain models
- deterministic sequential WorkOrchestrator
- `/work` API boundary
- EvaluationContract / EvaluationCase / EvaluationResult
- EvalRunner
- RecallPlannerContract / DeterministicRecallPlanner
- ContextProviderContract / MemoryContextProvider
- ContextAssemblerContract / DeterministicContextAssembler
- ContextBudgetPolicyContract / DeterministicContextBudgetPolicy
- TokenEstimatorContract / Utf8ByteTokenEstimator
- ContextRendererContract / MarkdownContextRenderer
- ContextInjectorContract / ReferenceMessageInjector
- ContextPreparationTrace / ContextTraceBuilder
- explicit ACCEPT / ABSTAIN recall semantics
- structured observability events
- Prometheus metrics
- OpenTelemetry tracing
- Tempo integration
- run_id correlation across model and tool execution
- automated unit and smoke tests
- persistent systemd deployment
- immutable release directories and rollback
- trusted self-development boundary
- disposable Worker workspaces
- supervised Worker subprocess execution
- trusted publication path through pull requests and CI

## Architecture

See [docs/architecture.md](docs/architecture.md).

Architecture decisions are recorded under [docs/adr](docs/adr).

Execution and experiment evidence is documented under [docs/evidence](docs/evidence) and [docs/validation](docs/validation).

## Development

Requirements:

- Python 3.12+
- virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,dsh]"
```

Run the main API:

```bash
uvicorn agent_platform.api.main:app \
  --host 127.0.0.1 \
  --port 8000
```

Run the MCP capability server:

```bash
uvicorn agent_platform.api.mcp:app \
  --host 127.0.0.1 \
  --port 8001
```

## Health and metrics

Main API:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/metrics
```

Tool/MCP metrics:

```bash
curl http://127.0.0.1:8001/metrics
```

## Quality gates

```bash
python -m compileall -q src tests scripts
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m mypy src
python -m pytest -v
python -m build
git diff --check
```

## Completed milestones

### V0 — Functional vertical slice

- [x] Platform-owned RuntimeContract.
- [x] Runtime implementation is replaceable.
- [x] DSH integrated as the first Runtime Adapter.
- [x] Platform-owned ModelContract.
- [x] OpenRouter integrated as a Model Adapter.
- [x] Provider credentials remain inside the platform boundary.
- [x] Internal OpenAI-compatible Model Gateway.
- [x] Platform-owned ToolContract and ToolRegistry.
- [x] MCP exposed as a capability adapter, not platform core.
- [x] Complete model -> tool -> model loop proven.
- [x] Structured logs, metrics and tracing.
- [x] Automated test suite and reproducible smoke validation.

### M5 — Persistent deployment

- [x] systemd lifecycle management.
- [x] automatic recovery and boot recovery.
- [x] immutable versioned releases.
- [x] health verification.
- [x] secret isolation.
- [x] roll-forward and rollback.
- [x] deployment observability.

See ADR-0003.

### M6 — Trusted self-development boundary

- [x] fail-closed ChangePolicy.
- [x] trusted publisher boundary.
- [x] disposable publication workspaces.
- [x] disposable Worker development workspaces.
- [x] Worker without GitHub publication credentials.
- [x] supervised subprocess execution and hard timeouts.
- [x] provider readiness checks and typed upstream failures.
- [x] safe Worker lifecycle diagnostics.
- [x] human-controlled promotion through pull requests and CI.

### M7 — Memory & Recall V0

- [x] platform-owned memory and retrieval contracts.
- [x] explicit durable memory writes.
- [x] SQLite persistence.
- [x] lexical-first retrieval with FTS5/BM25.
- [x] deterministic Retrieval Acceptance Gate.
- [x] explicit ACCEPT / ABSTAIN semantics.
- [x] scope isolation.
- [x] MCP capabilities through `memory_remember` and `memory_recall`.
- [x] cross-run persistence.
- [x] process recovery persistence.
- [x] guest reboot persistence.
- [x] application release persistence.

The guiding separation is:

```text
Memory != Retrieval != Context Injection
```

Embeddings, vector databases, hybrid retrieval, reranking and automatic memory extraction remain deferred until evidence demonstrates that the lexical baseline is insufficient.

See ADR-0005 and `docs/evidence/m7-memory-recall-results.md`.

### M8 — Evaluation Plane / Eval-as-Code

- [x] platform-owned EvaluationContract.
- [x] EvaluationCase / EvaluationResult canonical models.
- [x] deterministic EvalRunner.
- [x] PASS / FAIL / ERROR semantics.
- [x] machine-readable evidence artifacts.
- [x] evaluation kept distinct from observability, benchmark, tests and guardrails.

The guiding separation is:

```text
Eval != Observability != Benchmark != Test != Guardrail
```

See ADR-0006.

### M9 — Work API and deterministic orchestration

- [x] WorkRequest / WorkResult boundary.
- [x] explicit ContextRef allow-list attached to Work.
- [x] deterministic sequential WorkOrchestrator.
- [x] fail-fast behavior on the first failed step.
- [x] additive `/work` API.
- [x] contextual recall experiment with explicit namespace isolation.

The guiding separation is:

```text
Work != Plan != Run != Orchestrator != Runtime != Agent
```

See ADR-0007.

### M10 — Context Preparation + Injection V0

- [x] source-neutral canonical Context IR.
- [x] deterministic RecallPlannerContract.
- [x] Memory as the first ContextProvider implementation.
- [x] deterministic context assembly.
- [x] bounded deterministic context budgeting.
- [x] provider-neutral deterministic Markdown rendering.
- [x] privilege-safe injection at the canonical ModelRequest boundary.
- [x] structured ContextPreparationTrace evidence.
- [x] 8/8 Eval-as-Code acceptance cases passing.
- [x] deterministic end-to-end LinkedIn + Homelab smoke.
- [x] ADR-0008 accepted.

The guiding separation is:

```text
Context Source
!= Memory
!= Retrieval
!= Assembly
!= Budgeting
!= Rendering
!= Injection
```

Model-facing context and operational trace evidence remain separate.

See ADR-0008 and
`docs/evidence/m10-context-preparation-experiment-results.md`.

## Next steps

The next candidate milestone is **M11 — Context-Aware Work Execution V0**.

M11 should wire the accepted M10 context-preparation pipeline into actual
WorkStep execution so explicit Work contexts participate in the real Run /
Runtime path. It should also evaluate whether a first-class `ExecutionContext`
earns its place or whether a simpler boundary is sufficient.

The default `/work` execution path is therefore not yet context-aware end to end.

Dense retrieval, hybrid retrieval, reranking, automatic context selection,
LLM-based planning/compression and other retrieval complexity remain deferred
until evidence demonstrates a requirement gap or measurable improvement.
