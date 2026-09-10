# Agent Platform

A runtime-agnostic platform for executing, observing and evolving AI agents through explicit platform-owned contracts.

> Agent != Platform.

The platform is designed so runtimes, model providers and capability protocols remain replaceable.

## V0 status

The first functional vertical slice is complete.

```text
Agent Runtime
    |
    v
RuntimeContract
    |
    +----> Model Gateway -> ModelContract -> OpenRouter
    |
    +----> MCP Adapter -> ToolRegistry -> ToolContract -> Tool
```

The validated agentic loop is:

```text
DSH
 -> Agent Platform Model Gateway
 -> OpenRouter
 -> tool_call
 -> DSH
 -> MCP
 -> Agent Platform ToolRegistry
 -> DiagnosticEchoTool
 -> DSH
 -> Model Gateway
 -> OpenRouter
 -> final response
```

## Implemented

- RuntimeContract
- DeepSeek Harness runtime adapter
- ModelContract
- OpenRouter model adapter
- internal OpenAI-compatible Model Gateway
- ToolContract
- ToolRegistry
- MCP Streamable HTTP adapter
- diagnostic tool
- structured observability events
- Prometheus metrics
- OpenTelemetry tracing
- Tempo integration
- run_id correlation across model and tool execution
- automated unit and smoke tests

## Architecture

See [docs/architecture.md](docs/architecture.md).

Architecture decisions are recorded under [docs/adr](docs/adr).

V0 execution evidence is documented under [docs/validation](docs/validation).

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
ruff check src tests scripts
ruff format --check src tests scripts
mypy src
pytest -v
python -m build
git diff --check
```

## V0 Definition of Done

- [x] Platform-owned RuntimeContract.
- [x] Runtime implementation is replaceable.
- [x] DSH integrated as the first Runtime Adapter.
- [x] Platform-owned ModelContract.
- [x] OpenRouter integrated as a Model Adapter.
- [x] Provider credentials remain inside the platform boundary.
- [x] Internal OpenAI-compatible Model Gateway.
- [x] Platform-owned ToolContract and ToolRegistry.
- [x] MCP exposed as a capability adapter, not platform core.
- [x] Model-generated tool call executed successfully.
- [x] Tool result returned to the model.
- [x] Complete model -> tool -> model loop proven.
- [x] Structured logs.
- [x] Prometheus model and tool metrics.
- [x] OpenTelemetry tracing.
- [x] Tempo trace persistence.
- [x] Cross-process run_id correlation.
- [x] Automated test suite.
- [x] Reproducible smoke validation.
- [ ] Declarative homelab deployment.

The remaining deployment item is the next milestone rather than a V0 blocker.

## Next milestone

M5 focuses on operating the Agent Platform as a persistent workload:

- declarative deployment;
- service lifecycle;
- health/readiness;
- restart and recovery;
- secrets handling;
- Prometheus scraping from deployed services;
- dashboards and alerts;
- deployment verification and rollback.
