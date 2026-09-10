# Agent Platform — Architecture

## Purpose

The Agent Platform exists to execute, observe and govern AI agents without coupling the platform to a specific runtime, model provider or capability protocol.

The platform proves the following principle:

> Agent != Platform

Runtimes, model providers and tools are adapters behind platform-owned contracts.

## V0 architecture

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
                                v
                     +----------------------+
                     | OpenRouter Adapter   |
                     +----------------------+

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
| DiagnosticEchoTool   |
+----------------------+
```

## Core contracts

### RuntimeContract

Defines how an agent runtime executes a platform request. The first implementation is the DeepSeek Harness adapter. DSH is not part of the platform core and may be replaced by another runtime adapter.

### ModelContract

Defines provider-neutral model execution. The first implementation is OpenRouter. The internal Model Gateway exposes an OpenAI-compatible API so runtimes can use the platform without knowing the upstream provider.

### ToolContract

Defines platform-owned capabilities. Tools are registered in ToolRegistry and exposed externally through an MCP adapter. MCP is a capability protocol boundary, not the Tool implementation itself.

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
OpenRouter
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
DiagnosticEchoTool
      |
      | tool result
      v
DSH
      |
      v
Model Gateway
      |
      v
OpenRouter
      |
      v
Final response
```

## Execution correlation

`run_id` is the platform correlation identifier.

The same run_id is propagated through:

- RuntimeRequest
- DSH session id
- internal Model Gateway
- ModelRequest
- MCP HTTP header
- ToolRequest
- structured logs
- OpenTelemetry span attributes

Trace context is not yet propagated through every process boundary. V0 therefore correlates separate traces through run_id.

Distributed trace-context propagation is future work.

## Observability

### Logs

Structured events cover run lifecycle, model request lifecycle and tool request lifecycle. Tool arguments and outputs are not logged by default.

### Metrics

Model process:

- `agent_platform_model_requests_total`
- `agent_platform_model_request_duration_seconds`
- `agent_platform_model_tokens_total`

MCP/tool process:

- `agent_platform_tool_requests_total`
- `agent_platform_tool_request_duration_seconds`

Metrics are process-local and exposed by the process that owns the workload.

### Tracing

OpenTelemetry spans include:

- `model.gateway`
- `provider.openrouter`
- `tool.invoke`

Traces are exported through OTLP to Tempo.

## Process boundaries

Current local V0 topology:

```text
:8000  Agent Platform API / Model Gateway / metrics
:8001  MCP Tool Server / tool metrics
:4317  Tempo OTLP receiver in homelab
:3200  Tempo query API in homelab
```

## Security boundaries

The internal Model Gateway requires a bearer token through `MODEL_GATEWAY_API_KEY`.

The OpenRouter credential remains inside the platform process. The DSH runtime receives only the internal Model Gateway credential.

The MCP server is currently intended for trusted/local networking. Authentication, authorization and tool policy enforcement are outside V0 and must be addressed before exposing it to an untrusted network.

## V0 limitations

- Agent Platform workloads are still started manually.
- No production deployment lifecycle yet.
- No cross-process traceparent propagation.
- No policy engine for tool authorization.
- No persistent control plane.
- Only one diagnostic tool is implemented.
- MCP endpoint is not hardened for untrusted networks.

These limitations are intentional boundaries for V0.
