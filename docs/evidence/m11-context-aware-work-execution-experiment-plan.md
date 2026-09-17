# M11 Context-Aware Work Execution V0 Experiment Plan

- Status: Completed
- Date: 2026-09-17
- Decision: Accepted — Strategy B
- Governing principle: ADR-0002 — Evidence-Gated Architecture
- Related ADR: ADR-0009 — Context-Aware Work Execution V0
- Related capabilities:
  - ADR-0004 — Trusted Self-Development Boundary
  - ADR-0006 — Evaluation Plane / Eval-as-Code
  - ADR-0007 — Work API and Deterministic Orchestrator V0
  - ADR-0008 — Context Preparation and Injection V0

## Objective

Prove that explicit Work context can participate in actual agent execution through
the real Run / Runtime / internal Model Gateway path while preserving all accepted
M9 and M10 boundaries.

The target live path is:

```text
WorkRequest
  |
  v
WorkStep
  |
  v
M10 Context Preparation
  |
  v
run-scoped context binding
  |
  v
RunAgent
  |
  v
RuntimeContract
  |
  v
DSH Runtime
  |
  v
internal OpenAI-compatible Model Gateway
  |
  v
M10 ContextInjectorContract
  |
  v
ModelRequest
  |
  v
ModelGateway
  |
  v
ModelContract
```

## Baseline

The accepted baseline already provides:

```text
M9
  WorkRequest
  WorkStep
  WorkOrchestrator
  /work

M10
  deterministic recall planning
  MemoryContextProvider
  canonical Context IR
  deterministic assembly
  deterministic budgeting
  deterministic renderer
  privilege-safe ContextInjectorContract
  ContextPreparationTrace

Execution
  RunAgent
  RuntimeContract
  DSHRuntime
  run_id propagation
  DSH session_id = run_id
  internal Model Gateway resolves run_id from DSH session header
```

The current integration gap is:

```text
WorkOrchestrator
-> RunAgent(RunRequest(agent_id, step.input))
```

with no M10 preparation in the live path.

## Hypothesis

The platform can make Work execution context-aware with one small run-scoped
binding mechanism keyed by the existing `run_id`, while leaving:

```text
RuntimeRequest
DSHRuntime
ModelContract
provider adapters
```

free from context-source and retrieval-specific concepts.

A first-class `ExecutionContext` is not assumed to be necessary.

## Competing integration strategies

### Strategy A — prompt composition

Compose rendered context into the runtime prompt before DSH.

Measure:

- implementation size;
- determinism;
- privilege/message separation;
- compatibility with M10 contracts.

This strategy is expected to be simpler but may violate accepted M10 boundaries.

### Strategy B — run-scoped ModelRequest injection

Bind prepared context to `run_id`, then resolve it when the internal Model Gateway
receives DSH model traffic.

Measure:

- implementation size;
- concurrency isolation;
- lifecycle cleanup;
- model-turn behavior;
- preservation of M10 injection semantics;
- runtime/provider independence.

Strategy B is the leading hypothesis.

### Strategy C — first-class ExecutionContext

Evaluate only if Strategies A/B expose a semantic handoff that cannot be
represented cleanly by existing types.

Do not implement Strategy C preemptively.

## M11.0 — Architecture and experiment definition

Deliver:

```text
ADR-0009
M11 experiment plan
```

Freeze:

- integration alternatives;
- accepted M9/M10 invariants;
- run isolation requirements;
- failure semantics;
- success criteria;
- explicit deferrals.

## M11.1 — Context preparation application use case

Compose the accepted M10 components behind one application operation suitable for
Work execution.

Conceptually:

```text
prepare(
  objective,
  step_input,
  contexts,
  budget
)
-> execution-ready prepared context
```

### Experiment question

Does a dedicated result type earn its place?

Candidate:

```text
ContextPreparationResult
  rendered_context
  trace
```

Do not include intermediate Context IR values unless live execution needs them.

### Gate

Prove:

```text
same inputs -> same rendered hash
same inputs -> same trace
no contexts -> empty rendered context
ABSTAIN -> no rejected content
```

## M11.2 — Run-scoped context binding

Implement the smallest binding mechanism required by Strategy B.

Conceptual API:

```text
bind(run_id, rendered_context)
resolve(run_id)
release(run_id)
```

The exact class/contract name is not fixed.

### Required behavior

```text
exact run_id lookup
no global fallback
duplicate conflicting bind -> fail closed
release is idempotent
unknown resolve -> explicit absence
```

### Concurrency gate

Run at least two simultaneous bindings with different context hashes.

Expected:

```text
Run A -> Context A only
Run B -> Context B only
```

### Lifecycle gate

Verify release after:

```text
success
runtime exception
timeout/cancellation where testable
```

## M11.3 — Internal Model Gateway injection

Integrate run-scoped lookup into the existing OpenAI-compatible gateway mapping
path.

Order:

```text
incoming DSH request
-> resolve run_id
-> map canonical ModelRequest
-> resolve prepared context for run_id
-> ContextInjectorContract
-> ModelGateway.generate
```

Do not inject in OpenRouter/local provider adapters.

### Multi-turn gate

For one run, send more than one DSH-style model request.

Expected:

```text
each canonical ModelRequest receives the same prepared reference context
DSH-owned conversation does not accumulate injected messages
system messages remain unchanged
```

### Missing binding semantics

A model request that is declared context-required but has no binding must fail
closed.

Context-free Runs must continue without a binding.

The experiment may require a minimal way to distinguish these states.

## M11.4 — WorkStep integration

Wire context preparation into `WorkOrchestrator`.

Per step:

```text
work.objective
+ step.input
+ work.contexts
-> prepare context
-> RunAgent
```

### Required behavior

- one preparation per step;
- no inferred namespace;
- existing sequential ordering preserved;
- first failed step still stops Work;
- preparation failure prevents Runtime execution;
- completed step results remain preserved.

### Gate

Use a two-step Work with the same allow-list but different step inputs.

Expected:

```text
both steps stay within the allow-list
each step receives independently prepared evidence
step/run IDs remain distinguishable
```

## M11.5 — Real runtime composition

Replace unconditional application-level `FakeRuntime` composition with
configuration-driven runtime selection.

Required modes:

```text
fake
dsh
```

The exact configuration names should reuse existing deployment conventions where
possible.

### Requirements

- FakeRuntime remains available for deterministic tests.
- DSHRuntime becomes selectable for supervised real execution.
- missing DSH configuration fails clearly at startup/composition or readiness
  boundary;
- no runtime selection logic enters Work domain models.

### Gate

Prove application composition can instantiate both modes.

## M11.6 — Work / Run / Context trace correlation

Produce evidence that connects:

```text
work_id
step_id
run_id
context trace/hash
runtime/model execution
```

Prefer existing identifiers.

Add a new canonical trace type only if existing trace + WorkStepResult cannot
express the required evidence cleanly.

### Privacy gate

Default evidence must not include:

```text
raw recalled memory
raw recall query
credentials
tool arguments
model output
```

unless a specific evidence artifact intentionally captures them.

## M11.7 — Eval-as-Code

Create a machine-readable M11 suite using ADR-0006.

Required cases:

### Case 1 — Context-aware single-step Work

Expected:

```text
selected context prepared
binding created
runtime called
canonical model request receives reference context
binding released
Work succeeds
```

### Case 2 — No-context Work

Expected:

```text
no provider retrieval
no binding required
runtime executes unchanged
no injected context message
```

### Case 3 — Allow-list isolation

Provide relevant data in selected and unselected namespaces.

Expected:

```text
only selected namespace evidence participates
```

### Case 4 — Concurrent run isolation

Expected:

```text
Run A never receives Run B context
Run B never receives Run A context
```

### Case 5 — Runtime failure cleanup

Expected:

```text
Run fails
binding released
Work fails on that step
```

### Case 6 — Missing required binding

Expected:

```text
fail closed
no provider call with silently missing context
```

### Case 7 — Multi-turn model loop

Expected:

```text
same prepared context injected for every model request in one run
no duplicate accumulation in upstream conversation
```

### Case 8 — Runtime/provider independence

Expected:

```text
FakeRuntime path remains valid
DSH path does not expose context-source types
provider adapters remain unchanged
```

### Case 9 — Two-step Work

Expected:

```text
step-aware preparation
stable step ordering
separate run_id values
correlatable traces
```

## M11.8 — End-to-end deterministic integration smoke

Build one deterministic in-process smoke that exercises:

```text
WorkRequest
-> WorkOrchestrator
-> preparation
-> binding
-> RunAgent
-> fake/deterministic Runtime
-> DSH-style internal gateway request
-> injection
-> deterministic ModelContract
```

The smoke must verify exact:

```text
selected ContextRef values
prepared-context hash
run_id correlation
injected message role/order
system-message preservation
binding cleanup
WorkResult
```

No external model should be required for this acceptance gate.

## M11.9 — Supervised real DSH Work smoke

Run one controlled real-agent workload through:

```text
POST /work
-> DSHRuntime
-> internal Model Gateway
-> configured real ModelContract
```

Use a low-risk task whose output can demonstrate access to selected context.

Required evidence:

```text
work_id
step_id
run_id
prepared-context hash
DSH runtime execution
internal gateway model call
successful WorkResult
binding released
```

The live smoke is not a semantic benchmark.

It proves the production path is connected.

## M11.10 — Evidence and ADR decision

Capture:

```text
exact Git revision
full quality gate
Eval-as-Code artifact
deterministic integration smoke artifact
real DSH smoke evidence
implementation diff/complexity
binding lifecycle evidence
concurrency isolation evidence
deferred capabilities
```

Then decide:

```text
Accepted
Deferred
Rejected
```

## Expected accepted V0 shape

If Strategy B wins, the expected flow is approximately:

```text
WorkRequest
      |
      v
WorkOrchestrator
      |
      v
Context Preparation
      |
      v
RenderedContext + Trace
      |
      v
RunAgent
  allocates run_id
      |
      +------ bind(run_id, context)
      |
      v
RuntimeContract
      |
      v
DSHRuntime
  session_id = run_id
      |
      v
internal OpenAI-compatible endpoint
      |
      +------ resolve(run_id)
      |
      v
ReferenceMessageInjector
      |
      v
ModelGateway
      |
      v
ModelContract
      |
      v
response
      |
      v
release(run_id)
```

This is a hypothesis until evidence supports it.

## Explicitly not in scope

M11 does not require:

```text
automatic Context Resolver
parallel Work execution
DAG orchestration
persistent queue
scheduler
workflow engine
Redis
distributed binding store
automatic retry policy
cross-step artifacts
sandbox redesign
tool authorization policy engine
semantic retrieval
embedding retrieval
reranking
LLM query planning
LLM context compression
```

## Success criteria

M11 succeeds only if:

1. actual WorkStep execution uses M10 preparation;
2. explicit ContextRef allow-list remains authoritative;
3. preparation is step-aware;
4. RuntimeRequest remains free from memory/retrieval implementation details;
5. provider adapters remain context-agnostic;
6. context is injected at the canonical ModelRequest boundary;
7. system privilege is preserved;
8. no-context Runs remain backward-compatible;
9. concurrent Runs are isolated;
10. binding lifecycle is cleaned on success and failure;
11. missing required context state fails closed;
12. Work/step/run/context evidence is correlatable;
13. deterministic Eval-as-Code evidence passes;
14. deterministic integration smoke passes;
15. supervised real DSH `/work` smoke passes;
16. no queue/framework/distributed store is required.

## Decision rule

### Accept

Accept ADR-0009 if the platform can execute context-aware Work through the real
runtime/model path while preserving the accepted M9/M10 contracts and requiring
only complexity justified by the current single-node topology.

### Defer

Defer if context-aware execution requires a distributed/process boundary that the
current deployment cannot satisfy without additional infrastructure.

### Reject

Reject if the integration forces context concerns into runtime/provider adapters,
weakens privilege boundaries, or introduces state complexity without reliable
run isolation.

The governing rule remains:

> Complexity must earn its place.
