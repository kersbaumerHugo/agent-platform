# M14 — Usable Agent Runtime V1 — Results

- Status: Completed
- Date: 2026-09-21
- Governing principle: Complexity Must Earn Its Place / Evidence-Gated Architecture

## Executive result

M14 converted the previously tested Tool-Calling Runtime V0 into a real
configuration-driven Agent Platform runtime.

The accepted runtime path is:

```text
POST /runs
-> RunAgent
-> ToolCallingRuntime
-> ModelGateway
-> selected ModelContract adapter
-> model tool_call
-> ToolRegistry
-> capability authorization
-> typed capability
-> provider/backend
-> ToolResult
-> model final response
-> RunResult
```

## M14.1 — Shared Model Gateway Composition

Accepted.

Model provider construction moved into the shared composition root so the
internal OpenAI-compatible endpoint and ToolCallingRuntime reuse the same
provider configuration.

Supported provider implementations remain:

```text
OpenRouter
Local OpenAI-compatible
```

No new ModelContract abstraction was required.

## M14.2 — Agent Tool Registry Composition

Accepted.

The first production-composed capability path is:

```text
RepoWiseMCPClient
-> RepoWiseRepositoryBackend
-> RepositoryInspectionCapability
-> RepositoryInspectionTool
-> ToolRegistry
```

The runtime principal is:

```text
system:agent-runtime
```

The V1 grant is intentionally minimal:

```text
system:agent-runtime -> repository.inspect
```

`coding.execute` is not implicitly granted.

## M14.3 — Configurable Tool-Calling Runtime

Accepted.

The composition root now supports:

```text
AGENT_PLATFORM_RUNTIME=tool-calling
```

and composes:

```text
ModelGateway
+
ToolRegistry
+
trusted principal
->
ToolCallingRuntime
```

No RunAgent redesign was required.

## M14.4 — Real Local Model + Repository Inspection E2E

Accepted.

The live homelab inference path was:

```text
Agent Platform on dev01
-> LocalOpenAIModelAdapter
-> OpenAI-compatible HTTP endpoint
-> llama-server
-> local NVIDIA GPU
-> qwen3.5-9b-local
```

A direct provider preflight demonstrated native tool-call output:

```text
finish_reason = tool_calls
function = inspect_test
arguments = valid JSON object
```

The Agent Platform live `/runs` path then completed successfully through:

```text
RunAgent
-> ToolCallingRuntime
-> local model
-> repository_inspect
-> ToolRegistry
-> authorization
-> RepositoryInspectionCapability
-> RepoWise MCP
-> repository evidence
-> local model
-> successful RunResult
```

## Repository Evidence Fidelity Finding

The first live run succeeded operationally but exposed an evidence-quality gap.

RepoWise returned symbol information, but the original adapter preserved only:

```text
docs.summary
```

The local model therefore had insufficient evidence to precisely describe the
target file and resorted to speculation.

The real RepoWise response demonstrated that `docs.symbols` already contained:

```text
ToolDefinition
ToolRequest
normalize_principal_id
ToolResult
```

The smallest justified change was therefore to preserve provider-neutral
repository symbol evidence:

```text
name
kind
signature
line
```

No source-code dump, second RepoWise call, embedding pipeline, semantic search,
or new architectural layer was required.

After the change, the repeated live run correctly recovered the concrete
classes and method from repository evidence.

Decision:

```text
Repository symbol evidence -> accepted
Full source transport       -> deferred
Additional RepoWise calls   -> deferred
```

## M14.5 — Startup / Configuration Hardening

Accepted.

Tool-calling runtime composition now fails closed when:

```text
model configuration is invalid
repository path is missing
repository path does not exist
RepoWise command is blank
RepoWise executable cannot be resolved
```

Temporary model/network unavailability remains a runtime failure rather than a
startup dependency probe.

This avoids coupling API process startup to transient infrastructure health.

## Complexity Assessment

Complexity that earned its place:

```text
shared ModelGateway composition
real Agent ToolRegistry composition
trusted runtime principal
ToolCallingRuntime composition
repository symbol evidence
startup validation for static local dependencies
```

Complexity that did not earn its place:

```text
dynamic RBAC
roles / inheritance / wildcards
unbounded tool loop
full repository source injection
extra RepoWise retrieval round
semantic repository retrieval
startup network health dependency
distributed runtime state
new capability registry abstraction
```

## Final V1 Architecture

```text
Agent / Run
    |
    v
ToolCallingRuntime
    |
    +----> ModelGateway
    |         |
    |         v
    |      Model
    |
    v
Model tool call
    |
    v
ToolRegistry
    |
    v
Authorization
    |
    v
Typed Capability
    |
    v
Provider Backend
    |
    v
Typed Result
    |
    v
Model final response
```

## Live validation

The local model emitted a valid function tool call through the OpenAI-compatible
API. A real `/runs` request then completed successfully through the composed
ToolCallingRuntime and RepoWise-backed repository capability.

The first repository-aware run exposed an evidence-fidelity gap. Preserving
RepoWise symbol evidence fixed that gap without adding another provider call or
transporting full source code.

## Conclusion

M14 closes the gap between architectural capability support and a practically
usable agent runtime.

The Agent Platform can now execute a real repository-aware agent using a local
model and a real external capability provider through platform-owned contracts.

The V1 remains intentionally bounded.

> Complexity Must Earn Its Place.
