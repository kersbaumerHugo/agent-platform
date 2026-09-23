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
- supervised autonomous Worker execution;
- a configuration-driven tool-calling runtime;
- RepoWise-backed repository inspection through typed capabilities.

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
    +----> ToolRegistry
              |
              v
        Authorization
              |
              v
        Typed Capability
```

## Validated agentic loop

```text
RunAgent
 -> ToolCallingRuntime
 -> Model Gateway
 -> selected ModelContract adapter
 -> tool_call
 -> ToolRegistry
 -> Authorization
 -> Typed Capability
 -> Provider Backend
 -> ToolResult
 -> Model Gateway
 -> selected ModelContract adapter
 -> final response
```

## Implemented

- RuntimeContract
- DeepSeek Harness runtime adapter
- ToolCallingRuntime
- ModelContract
- OpenRouter model adapter
- local OpenAI-compatible model adapter
- local llama.cpp inference backend integration
- internal OpenAI-compatible Model Gateway
- ToolContract
- ToolRegistry
- typed CapabilityContract
- capability authorization boundary
- `repository.inspect`
- RepoWise MCP-backed repository inspection
- provider-neutral repository symbol evidence
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
- source-neutral context preparation pipeline
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

## Usable Agent Runtime V1

The platform can compose and execute a real tool-calling agent without manual
test wiring.

```text
POST /runs
    |
    v
RunAgent
    |
    v
ToolCallingRuntime
    |
    +----> ModelGateway
    |         |
    |         +----> OpenRouter
    |         |
    |         +----> Local OpenAI-compatible model
    |
    +----> ToolRegistry
              |
              v
        Authorization
              |
              v
      Typed Capability
              |
              v
      RepositoryInspection
              |
              v
        RepoWise over MCP
```

The first production-composed capability exposed to the agent runtime is:

```text
repository_inspect
    ->
repository.inspect
```

The runtime uses the platform-owned trusted principal:

```text
system:agent-runtime
```

Authorization remains explicit and fail closed.

RepoWise is kept outside the Agent Platform Python environment and is invoked
through MCP stdio as an isolated provider implementation.

Repository inspection preserves provider-neutral evidence including:

- target;
- summary;
- symbol name;
- symbol kind;
- symbol signature;
- source line;
- indexed revision;
- stale state.

The live local smoke was validated against the homelab OpenAI-compatible
inference endpoint backed by `llama-server` and the local NVIDIA GPU.

Example runtime configuration:

```bash
export AGENT_PLATFORM_RUNTIME=tool-calling

export MODEL_PROVIDER=local
export LOCAL_MODEL_BASE_URL=http://192.168.10.40:8080/v1
export LOCAL_MODEL_NAME=qwen3.5-9b-local
export LOCAL_MODEL_API_KEY=<secret>

export AGENT_PLATFORM_REPOSITORY_PATH="$PWD"
export AGENT_PLATFORM_REPOWISE_COMMAND="$HOME/.local/bin/repowise"
```

Start the API:

```bash
python -m uvicorn agent_platform.api.main:app \
  --host 127.0.0.1 \
  --port 8000
```

Example repository-aware run:

```bash
curl -sS \
  -X POST \
  http://127.0.0.1:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "agent_id": "developer-agent",
    "input": "You must use repository_inspect before answering. Inspect src/agent_platform/domain/tool.py and explain what the file defines using only the repository evidence."
  }'
```

The accepted V1 composition remains intentionally bounded:

```text
one model tool-call round
explicit capability grants
no dynamic RBAC
no autonomous tool loop
no distributed runtime state
no source-code dump required for repository structure inspection
```

Complexity remains evidence gated.

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

### M14 — Usable Agent Runtime V1

- [x] shared Model Gateway composition;
- [x] production Agent Tool Registry composition;
- [x] configuration-driven ToolCallingRuntime;
- [x] real local model tool calling;
- [x] RepoWise-backed repository inspection;
- [x] provider-neutral repository symbol evidence;
- [x] fail-closed validation of static runtime dependencies;
- [x] real `/runs` repository-aware smoke.

See `docs/evidence/m14-usable-agent-runtime-results.md`.

## Next steps

Build on the usable V1 runtime without widening platform abstractions unless new
evidence justifies it.

## Trusted Developer Agent

The platform enables supervised coding through a trusted development boundary:

- **Explicit capability authorization** - tools and actions require clear, typed capability grants;
- **Isolated coding execution** - Worker subprocesses run in disposable workspaces with bounded lifetimes;
- **Authoritative verification** - all tool results are validated through the platform-owned Authorization layer;
- **Trusted pull-request publication** - verified changes are published through platform-managed CI/CD paths.

This approach ensures that agent actions remain within a well-defined security envelope while maintaining developer control.
