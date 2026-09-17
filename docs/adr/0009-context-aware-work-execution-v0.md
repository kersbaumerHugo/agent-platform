# ADR-0009: Context-Aware Work Execution V0

- Status: Proposed
- Date: 2026-09-17
- Governing principle: ADR-0002 — Evidence-Gated Architecture
- Related decisions:
  - ADR-0004 — Trusted Self-Development Boundary
  - ADR-0006 — Evaluation Plane / Eval-as-Code
  - ADR-0007 — Work API and Deterministic Orchestrator V0
  - ADR-0008 — Context Preparation and Injection V0

## Trigger

M9 established an accepted Work boundary:

```text
WorkRequest
  + objective
  + explicit ContextRef[]
  + ordered WorkStep[]
```

M10 established an accepted deterministic context-preparation pipeline:

```text
ContextRef[]
-> RecallPlan
-> ContextProvider
-> ContextContribution[]
-> ContextBundle
-> BudgetedContextBundle
-> RenderedContext
-> privilege-safe ModelRequest injection
```

The remaining gap is execution.

The current Work execution path still invokes each step as a normal Run without
using the accepted M10 preparation pipeline.

Therefore the platform can currently:

```text
select context
prepare context
evaluate context
inject context in isolation
```

but has not yet demonstrated:

```text
WorkStep
-> prepared context
-> real Run
-> real Runtime
-> live Model Gateway
-> context-aware agent execution
```

M11 tests that integration.

## Problem statement

The platform needs to make explicit Work context participate in actual agent
execution without collapsing accepted boundaries.

The integration must preserve:

```text
Work != Run != Runtime != Agent
Context Preparation != Runtime Execution
Context Source != Runtime
Rendered Context != System Instruction
Runtime Adapter != Context Provider
Model Provider != Context Pipeline
```

M11 must not solve the gap by making DSH, model-provider adapters, or tools aware
of Memory, RetrievalHit, BM25, or ContextBundle.

## Accepted baseline

M11 starts from the following accepted facts:

```text
M9
  WorkRequest owns explicit ContextRef[]
  WorkOrchestrator executes ordered WorkStep values
  Work stops on first failed Run

M10
  explicit ContextRef[] remains authoritative
  preparation is deterministic
  Context IR is source-neutral
  rendering is deterministic
  injection occurs at canonical ModelRequest
  retrieved content is reference data, not system instruction
  ContextPreparationTrace is separate from model-facing content

Runtime
  RunAgent allocates run_id
  RuntimeRequest carries run_id
  DSH uses run_id as its session identifier
  internal OpenAI-compatible Model Gateway reconstructs run_id from the DSH
  session header
```

The existing `run_id` correlation is therefore the strongest candidate for
bridging Work preparation to live ModelRequest injection.

## Core integration question

M11 must determine the smallest mechanism that allows:

```text
prepared context for Run X
```

to be available when the internal Model Gateway receives model requests for:

```text
run_id = X
```

without forcing context data through provider-specific or runtime-specific APIs.

## Integration hypotheses

### Baseline — no context-aware execution

Current behavior:

```text
WorkStep
-> RunRequest(agent_id, input)
-> RunAgent
-> RuntimeRequest(run_id, agent_id, input)
-> Runtime
```

This remains the comparison baseline.

### Candidate A — prompt composition before Runtime

Conceptually:

```text
RenderedContext + WorkStep input
-> one composed RuntimeRequest.input
```

Advantages:

- very small implementation;
- no run-scoped state.

Costs:

- collapses rendering and execution concerns;
- bypasses the accepted M10 `ContextInjectorContract`;
- loses the explicit reference-message boundary;
- makes context representation part of runtime input semantics;
- weakens provider-neutral injection evidence.

Candidate A may be measured as a simplicity baseline, but it should not be
promoted if it violates accepted ADR-0008 properties.

### Candidate B — run-scoped context binding

Conceptually:

```text
WorkStep
  |
  v
Context Preparation
  |
  v
RenderedContext
  |
  v
RunAgent allocates run_id
  |
  +--> bind(run_id -> RenderedContext)
  |
  v
Runtime
  |
  v
DSH session_id = run_id
  |
  v
internal Model Gateway
  |
  +--> resolve(run_id)
  |
  v
ContextInjectorContract
  |
  v
ModelRequest
```

Advantages:

- preserves RuntimeRequest shape;
- keeps Runtime adapters context-agnostic;
- keeps model-provider adapters context-agnostic;
- reuses accepted M10 injection;
- reuses existing `run_id` correlation;
- supports every model turn in an agentic loop.

Costs:

- introduces run-scoped lifecycle state;
- requires bind / resolve / release behavior;
- requires concurrency and cleanup guarantees;
- an in-memory V0 backend assumes the Run and internal Model Gateway share a
  process.

Candidate B is the strongest initial hypothesis.

### Candidate C — first-class ExecutionContext

A new platform noun such as:

```text
ExecutionContext
```

must not be introduced merely because M10 mentioned it as a possibility.

M11 should promote it only if the integration requires a durable semantic
handoff that cannot be represented cleanly by existing models plus a small
run-scoped binding mechanism.

The experiment must explicitly answer:

```text
Did ExecutionContext earn its place?
```

## Context preparation application boundary

M10 validated the individual preparation components but did not require a single
application use case for live execution.

M11 may introduce a small composition boundary equivalent to:

```text
prepare(work, step)
-> prepared execution context
```

The result should expose only what execution needs.

A candidate minimal result is:

```text
RenderedContext
ContextPreparationTrace
```

If a dedicated `ContextPreparationResult` demonstrates independent semantic
value as the handoff between preparation and execution, it may be promoted.

Do not include intermediate IR values merely for convenience.

## Run-scoped binding lifecycle

If Candidate B is used, the lifecycle must be explicit:

```text
prepare
-> allocate run_id
-> bind
-> runtime execution
-> zero or more model calls resolve the same binding
-> release
```

Required properties:

- bind before the first model call;
- resolve by exact `run_id`;
- no fallback to another run;
- no implicit global context;
- no cross-run leakage;
- release on success;
- release on runtime failure;
- release on timeout/cancellation where supported;
- missing required binding fails closed rather than silently executing without
  expected context;
- context-free Runs continue to work without a binding.

The V0 binding may be process-local if current deployment evidence supports that
topology.

Persistent/distributed context binding is deferred.

## Agentic-loop behavior

DSH may make more than one model request during one Run.

M11 must verify that the same prepared reference context is injected into each
relevant canonical `ModelRequest` for that `run_id` without accumulating duplicate
context in DSH conversation state.

The platform must not mutate the DSH-owned conversation history.

## WorkStep semantics

Each WorkStep must prepare context using:

```text
work objective
step input
explicit Work ContextRef[]
```

The selected `ContextRef[]` remains the Work-level allow-list.

M11 must not infer additional namespaces.

The same Work may therefore prepare different relevant evidence for different
steps while using the same explicit context allow-list.

## Live Runtime composition

The current application composition still needs to prove the real runtime path.

M11 should provide configuration-driven composition so that:

```text
tests / deterministic local development
-> FakeRuntime

real supervised execution
-> DSHRuntime
```

The real runtime must not become hard-coded into domain or application logic.

Runtime selection is composition/configuration, not Work policy.

## Trace correlation

M11 must connect operational evidence across:

```text
work_id
step_id
run_id
ContextPreparationTrace
runtime execution
model requests
```

Do not add raw recalled content to default observability.

Prefer:

```text
IDs
hashes
versions
reason codes
counts
```

A new trace wrapper or correlation type must earn its place; existing identifiers
should be reused where sufficient.

## Failure semantics

M11 must preserve fail-closed execution.

Examples:

```text
required context preparation fails
-> step fails
-> runtime must not execute

required run-context binding fails
-> step fails
-> runtime must not execute

runtime fails
-> binding is released
-> Work stops on that step

model gateway cannot resolve a required binding
-> request fails closed
```

Context-free `/runs` behavior must remain backward-compatible.

## Security properties

M11 must preserve ADR-0008 privilege guarantees:

- retrieved/provider content is reference data;
- context must not become a new system message;
- existing system messages remain unchanged;
- Runtime adapters do not receive Memory or Retrieval internals;
- model-provider adapters remain context-agnostic;
- bindings are isolated by `run_id`;
- no raw context is added to default logs or metrics.

M11 does not grant additional tool authority.

Tool authorization remains a separate future concern.

## Evaluation

ADR-0006 should evaluate the live integration independently from subjective model
quality wherever possible.

Required deterministic cases should include:

```text
context-aware WorkStep uses only explicit contexts
different steps prepare independently
no-context Work executes without binding
two concurrent Runs cannot see each other's context
binding is released on success
binding is released on failure
missing required binding fails closed
every model turn for one run receives the same reference context
system messages remain unchanged
RuntimeRequest remains context-source agnostic
provider adapters remain context-agnostic
```

A supervised real DSH smoke should then prove the actual live path.

## Success criteria

ADR-0009 may be accepted only if M11 demonstrates:

1. `/work` can execute a WorkStep using the accepted M10 context-preparation
   pipeline.
2. Explicit Work `ContextRef[]` remains the only namespace allow-list.
3. Preparation remains step-aware through objective + step input.
4. Runtime adapters remain unaware of Memory, RetrievalHit, BM25 and ContextBundle.
5. Model-provider adapters remain context-agnostic.
6. Context reaches the canonical `ModelRequest` through the accepted privilege-safe
   injection policy.
7. Existing system messages remain unchanged.
8. Context-free Runs continue to work.
9. Two concurrent Runs remain context-isolated.
10. Run-scoped context is cleaned up on success and failure.
11. Missing required context state fails closed.
12. Work / step / run / context trace evidence is correlatable without raw context
    in default telemetry.
13. A deterministic integration suite emits machine-readable evidence.
14. A supervised real DSH Work smoke reaches the internal Model Gateway and
    completes successfully.
15. No new framework, queue, distributed state store, scheduler, or workflow engine
    is required for V0.

## Guardrails

M11 must not:

- make `RuntimeRequest` carry Memory or Retrieval-specific objects;
- make DSH responsible for retrieval or Context IR;
- inject context directly in provider adapters;
- promote retrieved content to system privilege;
- silently execute without required prepared context;
- use a global unscoped context variable;
- introduce automatic Context Resolver behavior;
- introduce a queue or workflow framework merely to connect Work to Run;
- introduce Redis or another distributed store without process-topology evidence;
- introduce `ExecutionContext` without demonstrated independent value;
- change `/runs` semantics unnecessarily;
- make real-runtime selection part of domain logic.

## Explicitly deferred

M11 V0 does not require:

```text
automatic Context Resolver
persistent Work queue
scheduler
distributed orchestration
persistent run-context registry
Redis
Kubernetes Jobs
parallel WorkStep execution
DAG execution
cross-step artifact propagation
automatic retries
semantic retrieval
reranking
LLM planning
tool authorization policy engine
sandbox backend replacement
```

These capabilities remain separate evidence-gated decisions.

## Experiment

This ADR remains **Proposed** until the experiment in:

```text
docs/evidence/m11-context-aware-work-execution-experiment-plan.md
```

is completed.

Expected results should be recorded in:

```text
docs/evidence/m11-context-aware-work-execution-results.md
```

## Decision rule

After the experiment:

- **Accepted** if context-aware Work execution reaches the real runtime/model path
  while preserving M9/M10 boundaries and run isolation.
- **Deferred** if the integration works but requires process/distribution changes
  not justified by the current deployment.
- **Rejected** if the proposed binding adds complexity without preserving or
  improving the accepted execution boundaries.

The governing rule remains:

> Complexity must earn its place.
