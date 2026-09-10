# V0 validation — agentic tool loop

Date: 2026-09-09

## Objective

Prove that an agent runtime can:

1. discover a platform capability;
2. expose it to the model;
3. receive a model-generated tool call;
4. execute the tool through the platform;
5. return the result to the runtime;
6. call the model again;
7. produce a final response;
8. correlate the execution through observability.

## Validated path

```text
DSH
 -> internal OpenAI-compatible Model Gateway
 -> ModelContract
 -> OpenRouter
 -> tool_call
 -> DSH
 -> MCP Streamable HTTP
 -> MCP Server Adapter
 -> ToolRegistry
 -> DiagnosticEchoTool
 -> DSH
 -> Model Gateway
 -> OpenRouter
 -> final answer
```

## Positive evidence

The successful run produced:

- two Model Gateway requests;
- one MCP `tools/call`;
- `tool.request.started`;
- `tool.request.succeeded`;
- final agent response after the tool result.

The same run_id was propagated through the model and tool paths.

## Tracing evidence

Tempo returned separate traces correlated by the same run_id.

The tool trace contained:

```text
span: tool.invoke
agent_platform.tool.name: diagnostic_echo
agent_platform.tool.status: succeeded
```

Separate traces are expected in V0 because trace context is not yet propagated through all runtime/process boundaries.

## Metrics evidence

The MCP process exposed:

```text
agent_platform_tool_requests_total{
  status="succeeded",
  tool="diagnostic_echo"
} 1
```

and a completed duration histogram observation.

The main API process did not report tool samples, proving that metrics remain owned by the process executing the workload.

## Regression gates

The validation branch passed:

- Python compilation
- Ruff lint
- Ruff formatting
- mypy
- pytest
- package build
- git diff whitespace validation

At validation time the suite contained 18 passing tests.

## Conclusion

The V0 proves a complete agent -> model -> tool -> model vertical slice using replaceable Runtime, Model and Tool boundaries.
