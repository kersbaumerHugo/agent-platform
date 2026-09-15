# Agent Platform

A runtime-agnostic platform for executing, observing and evolving AI agents through explicit platform-owned contracts.

> Agent != Platform.

The platform is designed so runtimes, model providers and capability protocols remain replaceable.

## Current status

The first functional vertical slice is complete and the platform now includes:

- a replaceable runtime boundary;
- provider-neutral model execution;
- OpenRouter and local OpenAI-compatible model adapters;
- a local llama.cpp inference backend;
- platform-owned tool capabilities exposed through MCP;
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
    +----> MCP Adapter -> ToolRegistry -> ToolContract -> Tool
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
ruff check src tests scripts
ruff format --check src tests scripts
mypy src
pytest -v
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

## Next milestone

### M7 — Memory & Recall V0

M7 introduces persistent platform-owned memory without coupling the platform to a vector database, embedding provider or automatic context-injection mechanism.

The V0 baseline is:

- platform-owned memory and retrieval contracts;
- explicit durable memory writes;
- SQLite persistence;
- lexical-first retrieval with FTS5/BM25;
- Retrieval Acceptance Gate;
- explicit abstention when evidence is insufficient;
- scope isolation;
- retrieval observability;
- cross-run and restart persistence validation.

The guiding separation is:

```text
Memory != Retrieval != Context Injection
```

Embeddings, vector databases, hybrid retrieval, reranking and automatic memory extraction remain deferred until evidence demonstrates that the lexical baseline is insufficient.

See ADR-0005.
