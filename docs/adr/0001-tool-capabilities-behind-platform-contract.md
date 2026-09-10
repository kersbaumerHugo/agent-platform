# ADR-0001: Tool capabilities live behind a platform-owned contract

- Status: Accepted
- Date: 2026-09-09

## Context

The Agent Platform needs to expose capabilities to agent runtimes without making the platform dependent on one runtime or capability protocol.

DeepSeek Harness supports MCP, but coupling platform tools directly to DSH or MCP would make either technology part of the platform core. That would violate the architectural goal that runtimes and protocols remain replaceable.

## Decision

The platform owns a ToolContract and ToolRegistry. Concrete tools implement ToolContract.

MCP is implemented as an adapter that:

1. discovers definitions from ToolRegistry;
2. exposes those definitions as MCP tools;
3. converts MCP calls into ToolRequest objects;
4. invokes ToolRegistry;
5. converts ToolResult back into MCP responses.

The DSH runtime consumes the MCP adapter as an external capability source. The model provider does not invoke platform tools directly.

## Consequences

### Positive

- Tool implementations are independent of DSH.
- Tool implementations are independent of MCP.
- Another runtime can reuse the same ToolRegistry.
- Another capability protocol can expose the same tools.
- Observability and future policy enforcement have one central invocation boundary.
- run_id correlation remains platform-owned.

### Negative

- More translation layers are required.
- Model tool-call semantics must be represented in ModelContract.
- MCP and Model Gateway require explicit protocol adapters.

## Observability decision

Tool observability is implemented at ToolRegistry rather than inside individual tools.

This guarantees consistent structured events, Prometheus metrics, OpenTelemetry spans, error handling and run_id correlation.

Tool arguments and outputs are not included in telemetry by default to avoid leaking secrets or personal data.

## Alternatives considered

### Implement tools directly inside DSH

Rejected because DSH would become part of platform capability logic.

### Make MCP the platform tool abstraction

Rejected because MCP is a transport/protocol boundary, not the domain contract.

### Let the model provider execute tools

Rejected because it couples capability execution to the provider and weakens platform governance.

## Result

The V0 validated the following real execution:

```text
DSH
 -> Model Gateway
 -> OpenRouter
 -> tool_call
 -> DSH
 -> MCP
 -> ToolRegistry
 -> DiagnosticEchoTool
 -> DSH
 -> Model Gateway
 -> OpenRouter
 -> final answer
```

The same run_id was observed across model and tool execution.
