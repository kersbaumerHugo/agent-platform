# Agent Platform — Architecture

## Purpose

The Agent Platform exists to execute, observe and govern AI agents without coupling the platform to a specific runtime, model provider, capability protocol or infrastructure backend.

The platform proves the principle:

> Agent != Platform

Runtimes, model providers, tools, deployment backends and memory backends remain adapters behind platform-owned contracts.

## Current architecture

```text
                     +----------------------+
                     |      DSH Runtime     |
                     |   Runtime Adapter    |
                     +----------+-----------+
                                |
                                | OpenAI-compatible API
                                v
                     +----------------------+
                     |    Model Gateway     |
                     |    ModelContract     |
                     +----------+-----------+
                                |
                     +----------+-----------+
                     |                      |
                     v                      v
              OpenRouter Adapter     Local OpenAI Adapter
                                            |
                                            v
                                      inference01
                                      llama-server
                                      Qwen3.5 9B

DSH
 |
 | MCP Streamable HTTP
 v
+----------------------+
| MCP Server Adapter   |
+----------+-----------+
           |
           v
+----------------------+
|     ToolRegistry     |
|     ToolContract     |
+----------+-----------+
           |
     +-----+-------------------------------+
     |                                     |
     v                                     v
Platform Tools                      Memory & Recall
                                          |
                         +----------------+----------------+
                         |                                 |
                         v                                 v
                  memory_remember                    memory_recall
                         |                                 |
                         v                                 v
                MemoryStoreContract                 RetrievalContract
                         |                                 |
                         v                                 v
                       SQLite                       SQLite FTS5/BM25
                                                           |
                                                           v
                                               Retrieval Acceptance Gate
                                                   ACCEPT / ABSTAIN
```

## Work and Context Preparation plane

M9 and M10 add an application-level path above the existing runtime/model/tool
boundaries:

```text
WorkRequest
  |
  +--> objective
  +--> explicit ContextRef[]
  +--> WorkStep[]
             |
             v
      WorkOrchestrator
             |
             v
      RecallIntent
             |
             v
 DeterministicRecallPlanner
             |
             v
      RecallPlan
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

This pipeline has been validated independently through Eval-as-Code and an
end-to-end deterministic smoke.

The current default Work execution path does **not yet** invoke this preparation
pipeline before `RunAgent`. Wiring the accepted M10 subsystem into real WorkStep
execution is the next candidate milestone.

## Core contracts

### RuntimeContract

Defines how an agent runtime executes a platform request.

The first implementation is the DeepSeek Harness adapter.

DSH is not part of the platform core and may be replaced by another runtime adapter.

### ModelContract

Defines provider-neutral model execution.

Current implementations include:

- OpenRouterModelAdapter;
- LocalOpenAIModelAdapter.

The internal Model Gateway exposes an OpenAI-compatible API so runtimes can use the platform without knowing the selected upstream provider or inference backend.

### ToolContract

Defines platform-owned capabilities.

Tools are registered in ToolRegistry and exposed externally through an MCP adapter.

MCP is a capability protocol boundary, not the tool implementation itself.

### MemoryStoreContract

Defines durable platform-owned memory persistence independently of the storage backend.

The current adapter is SQLite.

### RetrievalContract

Defines provider-neutral recall/search behavior.

The current adapter uses SQLite FTS5 with BM25 ranking.

### RetrievalAcceptanceContract

Defines whether retrieved evidence is sufficient to use.

The current deterministic implementation returns ACCEPT or ABSTAIN based on lexical evidence and scope constraints.

### EvaluationContract

Defines deterministic evaluation independently from runtime observability,
benchmarks, tests and guardrails.

The Evaluation Plane uses canonical EvaluationCase / EvaluationResult values and
an EvalRunner to emit machine-readable PASS / FAIL / ERROR evidence.

### Work boundary

`WorkRequest` represents an objective, an explicit `ContextRef[]` allow-list and
one or more deterministic WorkStep values.

The V0 WorkOrchestrator executes steps sequentially and stops on the first failed
Run.

### Context preparation contracts

The accepted M10 behavioral seams are:

- RecallPlannerContract;
- ContextProviderContract;
- ContextAssemblerContract;
- ContextBudgetPolicyContract;
- TokenEstimatorContract;
- ContextRendererContract;
- ContextInjectorContract.

The canonical Context IR remains source-neutral. Memory is one provider
implementation rather than the definition of Context.

## Model-provider flow

```text
Runtime
   |
   v
Model Gateway
   |
   v
ModelContract
   |
   +--------------------+
   |                    |
   v                    v
OpenRouter         Local OpenAI Adapter
                        |
                        v
                   llama-server
                        |
                        v
                   local model
```

Provider selection remains intentionally minimal and configuration-driven.

Routing, fallback and provider arbitration are not part of the current baseline.

## Agentic tool flow

```text
User instruction
      |
      v
DSH Runtime
      |
      v
Model Gateway
      |
      v
Selected Model Provider
      |
      | tool_call
      v
DSH
      |
      | MCP tools/call
      v
MCP Server Adapter
      |
      v
ToolRegistry
      |
      v
Platform Tool
      |
      | tool result
      v
DSH
      |
      v
Model Gateway
      |
      v
Selected Model Provider
      |
      v
Final response
```

## Memory & Recall flow

```text
Agent / Runtime
      |
      | capability call
      v
MCP Adapter
      |
      v
ToolRegistry
      |
      +----------------------+
      |                      |
      v                      v
memory_remember         memory_recall
      |                      |
      v                      v
MemoryStoreContract    RetrievalContract
      |                      |
      v                      v
SQLite                 SQLite FTS5 / BM25
                             |
                             v
                  Retrieval Acceptance Gate
                             |
                       ACCEPT / ABSTAIN
```

The guiding separation is:

```text
Memory != Retrieval != Context Injection
```

Memory owns durable persistence.

Retrieval owns search and ranking.

The Retrieval Acceptance Gate decides whether retrieved evidence is sufficient to return.

Memory recall itself does not inject context.

M10 adds a separate accepted context-preparation and privilege-safe injection
pipeline downstream from explicit context selection. Retrieved/provider content
is treated as reference data and is never promoted into a new system message by
structure.

The remaining integration gap is operational: the default WorkOrchestrator still
passes only `agent_id` and step input into `RunAgent`, so M10 preparation is not
yet part of the real `/work` execution path.

## Context preparation and injection

The accepted deterministic V0 flow is:

```text
explicit ContextRef[]
      |
      v
RecallIntent
      |
      v
RecallPlan
      |
      v
ContextProviderContract(s)
      |
      v
ContextContribution[]
      |
      v
ContextBundle
      |
      v
BudgetedContextBundle
      |
      v
RenderedContext
      |
      v
ModelRequest
```

Key properties:

- explicit M9 ContextRef values remain the allow-list boundary;
- no implicit namespace discovery is performed;
- MemoryContextProvider normalizes memory/retrieval evidence into source-neutral
  ContextContribution values;
- assembly, budgeting, rendering and injection are deterministic;
- provider-specific retrieval scores do not leak into model-facing context;
- budgeting reserves bounded capacity before injection;
- rendered context is injected using a user-role reference message;
- operational evidence is stored separately in ContextPreparationTrace;
- raw recalled context and recall query text are not copied into default trace
  evidence.

The accepted V0 deliberately does not require embeddings, reranking, an LLM
planner, context summarization, a vector database, GraphRAG or an external RAG
framework.

## Deployment architecture

The accepted homelab deployment uses:

- systemd;
- Python virtual environments;
- immutable versioned release directories;
- an atomic `current` symlink;
- host-local configuration and secret files;
- persistent application state outside immutable releases.

Conceptually:

```text
/opt/agent-platform/
├── releases/
│   ├── <release-a>/
│   │   ├── app/
│   │   ├── .venv/
│   │   └── REVISION
│   └── <release-b>/
│       ├── app/
│       ├── .venv/
│       └── REVISION
└── current -> releases/<active-release>

/var/lib/agent-platform/
└── memory/
    └── memory.sqlite3
```

Application release replacement does not delete durable memory.

Deployment infrastructure remains subordinate to platform requirements and is not part of the Agent Platform domain model.

## Trusted self-development boundary

Self-development is separated into untrusted development and trusted publication.

```text
Work Item
   |
   v
Disposable Worker Workspace
   |
   v
Worker / DSH
   |
   v
ChangeSet
   |
   v
Trusted Publication Boundary
   |
   v
ChangePolicy
   |
   v
Branch / Pull Request
   |
   v
CI + Human Approval
```

Security properties:

- Worker output is a proposal, never authority.
- Worker receives no GitHub publication credential.
- Worker cannot modify trusted acceptance mechanisms directly.
- Protected changes fail closed.
- Publication occurs through a trusted boundary.
- No auto-merge authority is granted to the Worker.

## Execution correlation

`run_id` is the platform correlation identifier.

The same `run_id` is propagated through:

- RuntimeRequest;
- DSH session id;
- internal Model Gateway;
- ModelRequest;
- MCP HTTP header;
- ToolRequest;
- structured logs;
- OpenTelemetry span attributes.

Trace context is not yet propagated through every process boundary.

The current baseline therefore correlates separate traces through `run_id`.

## Observability

### Logs

Structured events cover:

- run lifecycle;
- model request lifecycle;
- tool request lifecycle;
- bounded Worker lifecycle diagnostics.

Prompts, tool arguments, file contents, model outputs, memory content and credentials are not logged by default.

### Metrics

Model process:

- `agent_platform_model_requests_total`;
- `agent_platform_model_request_duration_seconds`;
- `agent_platform_model_tokens_total`.

MCP/tool process:

- `agent_platform_tool_requests_total`;
- `agent_platform_tool_request_duration_seconds`.

Metrics are process-local and exposed by the process that owns the workload.

Dedicated retrieval-quality metrics remain an evidence-gated follow-up.

### Tracing

OpenTelemetry spans include provider and capability boundaries, including:

- `model.gateway`;
- `provider.openrouter`;
- `provider.local_openai`;
- `tool.invoke`.

Traces are exported through OTLP to Tempo.

## Process boundaries

Current homelab topology:

```text
192.168.10.30:8000    Agent Platform API / Model Gateway / metrics
192.168.10.30:8001    MCP Tool Server / tool metrics
192.168.10.40:8080    authenticated local inference backend
192.168.10.20:4317    Tempo OTLP receiver
192.168.10.20:3200    Tempo query API
```

## Security boundaries

The internal Model Gateway requires a bearer token through `MODEL_GATEWAY_API_KEY`.

Provider credentials remain inside the platform boundary.

M10 adds an instruction-privilege boundary: retrieved/provider context is injected
as reference data through a user-role ModelMessage while existing system messages
remain unchanged.

OpenRouter credentials are retained by the platform process.

The local inference credential is used only by the Local OpenAI adapter.

The DSH runtime receives only the internal Model Gateway credential.

The MCP server remains intended for trusted/local networking until authentication, authorization and tool policy enforcement are explicitly implemented.

Memory retrieval requires an explicit namespace and never searches outside that scope.

Durable memory lives outside immutable application releases under the persistent-state boundary.

## M7 validation status

M7 Memory & Recall V0 is accepted.

Validated behavior includes:

- explicit write through `memory_remember`;
- recall through `memory_recall`;
- deterministic lexical ranking baseline;
- explicit ABSTAIN for unrelated queries;
- scope isolation;
- persistence across separate executions;
- persistence after MCP SIGKILL and systemd recovery;
- persistence after complete guest reboot;
- persistence across application roll-forward.

See:

```text
docs/adr/0005-memory-recall-v0.md
docs/evidence/m7-memory-recall-results.md
```

## M8 validation status

M8 Evaluation Plane / Eval-as-Code is accepted.

Validated behavior includes:

- platform-owned evaluation contracts;
- deterministic evaluation execution;
- PASS / FAIL / ERROR outcomes;
- machine-readable evidence artifacts;
- explicit separation from observability, benchmark, test and guardrail concerns.

See ADR-0006.

## M9 validation status

M9 Work API and deterministic orchestration is accepted.

Validated behavior includes:

- explicit WorkRequest / WorkResult boundaries;
- sequential deterministic WorkStep execution;
- fail-fast behavior on the first failed Run;
- explicit ContextRef allow-list propagation at the Work boundary;
- additive `/work` API;
- deterministic contextual recall experiments.

See ADR-0007.

## M10 validation status

M10 Context Preparation + Injection V0 is accepted.

Validated behavior includes:

- source-neutral Context IR;
- deterministic recall planning;
- Memory as a Context Provider;
- deterministic context assembly;
- bounded deterministic budgeting;
- byte-stable Markdown rendering;
- privilege-safe injection through canonical ModelRequest;
- structured ContextPreparationTrace evidence;
- 8/8 deterministic Eval-as-Code acceptance cases;
- deterministic end-to-end LinkedIn + Homelab smoke.

See:

```text
docs/adr/0008-context-preparation-injection-v0.md
docs/evidence/m10-context-preparation-experiment-results.md
docs/evidence/artifacts/m10-context-preparation-v0.json
docs/evidence/artifacts/m10-context-preparation-smoke-v0.json
```

## Current limitations

- No cross-process traceparent propagation.
- No general policy engine for tool authorization.
- No persistent control plane.
- MCP is not hardened for untrusted networks.
- Provider routing/fallback is intentionally minimal.
- Semantic retrieval is not justified by current evidence.
- Automatic memory extraction is not implemented.
- The accepted M10 context-preparation/injection pipeline is not yet wired
  into the default `/work` execution path.
- The default FastAPI `/runs` and `/work` composition still instantiates
  `FakeRuntime`; the real DSH Runtime Adapter exists but is not yet the default
  Work execution composition.
- ContextPreparationTrace is not yet correlated with Work/Run lifecycle evidence
  in the live execution path.
- Dedicated retrieval-quality metrics are not yet implemented.
- Persistent SQLite file creation permissions need deployment hardening so restrictive mode is automatic.

These limitations are intentional and subject to evidence-gated evolution.
