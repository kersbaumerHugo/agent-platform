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

Automatic context injection is not part of the current baseline.

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

## Current limitations

- No cross-process traceparent propagation.
- No general policy engine for tool authorization.
- No persistent control plane.
- MCP is not hardened for untrusted networks.
- Provider routing/fallback is intentionally minimal.
- Semantic retrieval is not justified by current evidence.
- Automatic memory extraction is not implemented.
- Automatic context injection is not implemented.
- Dedicated retrieval-quality metrics are not yet implemented.
- Persistent SQLite file creation permissions need deployment hardening so restrictive mode is automatic.

These limitations are intentional and subject to evidence-gated evolution.
