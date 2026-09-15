# Agent Platform — Architecture

## Purpose

The Agent Platform exists to execute, observe and govern AI agents without coupling the platform to a specific runtime, model provider, capability protocol or infrastructure backend.

The platform proves the principle:

> Agent != Platform

Runtimes, model providers, tools, deployment backends and future memory backends remain adapters behind platform-owned contracts.

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
           v
+----------------------+
| Platform Capability  |
+----------------------+
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

## Deployment architecture

The accepted homelab deployment uses:

- systemd;
- Python virtual environments;
- immutable versioned release directories;
- an atomic `current` symlink;
- host-local configuration and secret files.

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
```

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

Prompts, tool arguments, file contents, model outputs and credentials are not logged by default.

### Metrics

Model process:

- `agent_platform_model_requests_total`;
- `agent_platform_model_request_duration_seconds`;
- `agent_platform_model_tokens_total`.

MCP/tool process:

- `agent_platform_tool_requests_total`;
- `agent_platform_tool_request_duration_seconds`.

Metrics are process-local and exposed by the process that owns the workload.

### Tracing

OpenTelemetry spans include provider and capability boundaries, including:

- `model.gateway`;
- `provider.openrouter`;
- `provider.local_openai`;
- `tool.invoke`.

Traces are exported through OTLP to Tempo.

## Process boundaries

Current local topology:

```text
:8000                 Agent Platform API / Model Gateway / metrics
:8001                 MCP Tool Server / tool metrics
192.168.10.40:8080    authenticated local inference backend
:4317                 Tempo OTLP receiver in homelab
:3200                 Tempo query API in homelab
```

## Security boundaries

The internal Model Gateway requires a bearer token through `MODEL_GATEWAY_API_KEY`.

Provider credentials remain inside the platform boundary.

OpenRouter credentials are retained by the platform process.

The local inference credential is used only by the Local OpenAI adapter.

The DSH runtime receives only the internal Model Gateway credential.

The MCP server remains intended for trusted/local networking until authentication, authorization and tool policy enforcement are explicitly implemented.

## M7 — Memory & Recall target architecture

M7 introduces persistent memory as a separate platform capability.

The separation is:

```text
Memory != Retrieval != Context Injection
```

Target V0:

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

### Memory

Memory owns durable persistence.

V0 memory writes are explicit.

Automatic extraction from every conversation or model response is deferred.

### Retrieval

Retrieval owns search and ranking.

The V0 baseline is lexical-first using SQLite FTS5/BM25.

### Retrieval Acceptance Gate

The Retrieval Acceptance Gate decides whether retrieved evidence is sufficient to use.

Retrieval must be allowed to abstain.

Top-k returning results does not imply that the context is relevant enough.

### Context injection

Automatic context injection is not part of M7 V0.

The initial integration surface is the existing platform capability boundary.

If later evidence shows that explicit recall materially limits task success, an automatic Context Builder may be evaluated separately.

## Persistent state boundary

Memory state must not live inside immutable application release directories.

Conceptually:

```text
/var/lib/agent-platform/
└── memory/
    └── ...
```

The exact storage layout remains a deployment concern.

Application release replacement must not delete durable memory.

## Current limitations

- No cross-process traceparent propagation.
- No general policy engine for tool authorization.
- No persistent control plane.
- Memory and recall are not yet implemented.
- MCP is not hardened for untrusted networks.
- Provider routing/fallback is intentionally minimal.
- Semantic retrieval is not justified by current evidence.

These limitations are intentional and subject to evidence-gated evolution.
