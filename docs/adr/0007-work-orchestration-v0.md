# ADR-0007: Work API and Deterministic Orchestrator V0

- Status: Proposed
- Date: 2026-09-16
- Governing principle: ADR-0002 — Evidence-Gated Architecture
- Related decisions:
  - ADR-0005 — Memory & Recall V0
  - ADR-0006 — Evaluation Plane / Eval-as-Code

## Trigger

The Agent Platform can already execute a `RunRequest` through `RunAgent`, but a
run is still a low-level execution primitive.

The platform does not yet have a first-class representation of user-level work
that can:

- group one or more execution steps;
- preserve an explicit execution order;
- carry contextual intent across the work;
- distinguish delivery context from subject context;
- expose work-level state independently from individual runs;
- coordinate existing run execution without coupling orchestration to a runtime
  or model provider.

The current `/runs` API remains useful as a low-level execution boundary, but it
is not sufficient as the long-term user/work boundary.

## Principle

The architecture must preserve the following distinctions:

```text
Work != Plan != Run != Orchestrator != Runtime != Agent
```

### Work

A user-level unit of intent.

Examples:

- publish a LinkedIn post about the homelab;
- analyze an architecture decision;
- prepare and verify a generated artifact.

### Plan

An explicit ordered description of execution steps required to perform a work
item.

M9 V0 does not require automatic plan generation.

### Run

One concrete execution attempt of an agent/runtime request.

### Orchestrator

Coordinates work execution and run sequencing.

It does not become the runtime itself.

### Runtime

Executes an agent request through an implementation-specific backend.

### Agent

Owns task behavior and capability usage.

The orchestrator must not absorb agent semantics.

## Current baseline

The accepted baseline is:

```text
POST /runs
   |
   v
RunRequest
   |
   v
RunAgent
   |
   v
RuntimeContract
   |
   v
Runtime
```

This already provides:

- run identity;
- run lifecycle;
- runtime execution;
- observability;
- success/failure state.

M9 must reuse this baseline rather than replacing it.

## Proposed decision

Experiment with a minimal, deterministic Work API and Orchestrator V0.

Conceptually:

```text
WorkRequest
    |
    +--> objective
    +--> explicit context selection
    +--> ordered steps
    |
    v
WorkOrchestrator
    |
    v
WorkPlan
    |
    +--> WorkStep 1 --> RunAgent --> RunResult
    |
    +--> WorkStep 2 --> RunAgent --> RunResult
    |
    ...
    |
    v
WorkResult
```

The first implementation should remain synchronous and in-process.

No queue, scheduler, workflow engine, distributed coordinator, or LLM planner is
required for V0.

## Explicit context composition

M9 must preserve the contextual-memory requirement discovered before the
milestone.

A work item may legitimately belong to more than one memory context.

Example:

```text
Task:
  write a LinkedIn post about the homelab

Context:
  shared   -> global
  delivery -> app:linkedin
  subject  -> project:homelab
```

Another example:

```text
Task:
  write a LinkedIn post about Agent Platform

Context:
  shared   -> global
  delivery -> app:linkedin
  subject  -> project:agent-platform
```

Cross-context composition is valid when it is explicit.

The unsafe behavior is unrestricted retrieval across all memory namespaces.

The V0 rule is therefore:

> Cross-context composition is explicit and allow-listed by the work request.

## Proposed context shape

M9 may introduce an equivalent of:

```text
ContextRef
  role:
    - shared
    - delivery
    - subject
  namespace:
    - global
    - app:linkedin
    - project:homelab
    - project:agent-platform
```

A work request may carry multiple context references.

Example:

```json
{
  "objective": "Write a LinkedIn post about the homelab",
  "contexts": [
    {
      "role": "shared",
      "namespace": "global"
    },
    {
      "role": "delivery",
      "namespace": "app:linkedin"
    },
    {
      "role": "subject",
      "namespace": "project:homelab"
    }
  ]
}
```

The exact names are implementation details until the experiment validates them.

## Context behavior in M9 V0

M9 V0 is responsible for:

- receiving explicit context references;
- validating them;
- preserving them across orchestration;
- making the active context set available to work execution;
- preventing accidental implicit access to unrelated contexts.

M9 V0 is not required to implement:

- automatic context inference;
- automatic scope selection;
- semantic context routing;
- global memory search;
- automatic context expansion.

Those remain future evidence-gated capabilities.

## Relationship to Memory & Recall

M9 does not replace the M7 memory model.

Existing `MemoryScope(namespace=...)` remains the storage/retrieval isolation
primitive.

Conceptually:

```text
WorkRequest
    |
    v
explicit ContextRef[]
    |
    v
allowed MemoryScope[]
    |
    v
Retrieval
```

A future Context Resolver may automate selection of allowed scopes only after
manual/explicit context selection demonstrates material friction.

That future capability is not part of M9 V0.

## Planning policy

M9 V0 uses an explicit deterministic plan.

The platform should not introduce an LLM planner merely to justify an
orchestrator.

The initial plan may be supplied directly by the caller or constructed by a
small deterministic application service.

Automatic decomposition from an objective into steps is deferred.

This keeps:

```text
Planning != Orchestration
```

## Execution policy

The smallest useful orchestration policy should be:

```text
ordered sequential execution
stop on failure
preserve completed step results
return work-level outcome
```

Parallel execution, DAG scheduling, retries, compensation, resumability, and
distributed coordination are deferred.

## Proposed minimum concepts

The experiment may introduce equivalents of:

```text
WorkRequest
WorkStep
WorkStatus
WorkResult
ContextRef
ContextRole
WorkOrchestrator
```

A separate `WorkPlan` type should only be introduced if implementation evidence
shows that the plan needs an identity/lifecycle distinct from the request.

## Work-level status

The initial status vocabulary should remain small:

```text
PENDING
RUNNING
SUCCEEDED
FAILED
```

Additional states such as:

```text
PAUSED
CANCELLED
WAITING
RETRYING
PARTIALLY_SUCCEEDED
```

are deferred until a concrete workflow requires them.

## API

The experiment should expose a Work API separate from `/runs`.

Conceptually:

```text
POST /work
```

or an equivalent resource-oriented path selected during implementation.

The Work API should:

- accept a work request;
- execute through the WorkOrchestrator;
- return a structured work result;
- preserve existing `/runs` behavior.

The exact HTTP resource naming is not architectural and may be adjusted during
implementation.

## Observability

Work orchestration should use the existing observability approach.

Useful work-level signals may include:

- work started;
- work succeeded;
- work failed;
- work ID;
- step count;
- completed step count;
- failed step identifier;
- total duration.

Sensitive task input and memory content must not be copied into default telemetry.

## Evaluation

ADR-0006 should be used to evaluate M9.

The first deterministic orchestration evaluation should verify at least:

```text
single-step work succeeds
multi-step work preserves order
later step is not executed after failure
completed step results are preserved
explicit context references are preserved
unselected contexts are not silently added
same deterministic work produces reproducible structure
```

This gives the Work/Orchestrator experiment executable acceptance evidence.

## Success criteria

ADR-0007 may be accepted only if the M9 experiment demonstrates:

1. work can be represented independently from a run;
2. one work can coordinate multiple ordered run steps;
3. the orchestrator reuses `RunAgent` rather than duplicating runtime execution;
4. step ordering is deterministic;
5. failure stops subsequent execution under the V0 policy;
6. completed step results remain inspectable after failure;
7. work-level status is distinct from individual run status;
8. explicit multi-context references can be represented and preserved;
9. unrelated memory contexts are not implicitly added;
10. orchestration remains independent from a model provider and runtime backend;
11. no external workflow framework, queue, or persistent control plane is
    required for V0;
12. M8 Eval-as-Code can evaluate the orchestration behavior.

## Guardrails

M9 must not:

- replace `RunAgent`;
- duplicate `RuntimeContract`;
- make the orchestrator an agent;
- make the orchestrator a model planner;
- search all memory namespaces by default;
- infer contextual memory scopes automatically in V0;
- introduce Celery, Temporal, Airflow, Kafka, RabbitMQ, Kubernetes Jobs, or an
  equivalent orchestration dependency without evidence;
- add retries before retry semantics are defined;
- add parallelism before a workload needs it;
- add persistence before restart/resume requirements are proven;
- make orchestration responsible for architectural promotion;
- expose sensitive task/context content in default observability.

## Alternatives

### Keep only `/runs`

This remains the baseline.

It is sufficient if there is no demonstrated need for user-level multi-step work
coordination.

### Adopt a workflow framework immediately

Deferred.

The platform has not yet demonstrated requirements for durable scheduling,
distributed workers, long-running workflows, compensation, or event-driven
resumption.

### Minimal internal deterministic orchestrator

Proposed experiment.

This is the smallest candidate capable of proving whether a Work abstraction
provides value above individual runs.

## Consequences if accepted

### Positive

- user-level work becomes distinct from execution attempts;
- multi-step execution gains an explicit coordination boundary;
- context intent can be carried at work level;
- memory-context composition can remain explicit and auditable;
- future planners can target a stable orchestration boundary;
- future durable workflow engines can remain replaceable implementation choices;
- M8 evaluation can measure orchestration behavior.

### Negative

- the platform gains another domain abstraction;
- work/run relationships require maintenance;
- work result shapes may evolve when persistence/resume appears;
- context references create a contract that must remain semantically clear;
- poorly scoped orchestration can drift toward a workflow engine.

## Explicitly deferred

M9 V0 does not accept:

- LLM plan generation;
- automatic Context Resolver;
- cross-context global retrieval;
- DAG scheduling;
- parallel steps;
- automatic retries;
- compensation/saga behavior;
- persistent work database;
- queue/broker;
- distributed workers;
- scheduled work;
- event-driven resumption;
- human approval nodes;
- workflow UI;
- external orchestration framework.

Each must earn its place independently.

## Experiment

This ADR remains **Proposed** until the experiment in:

```text
docs/evidence/m9-work-orchestration-experiment-plan.md
```

is completed.

Expected results should be recorded in:

```text
docs/evidence/m9-work-orchestration-experiment-results.md
```

## Decision rule

After the experiment:

- **Accepted** if Work + deterministic orchestration provides reusable value
  above direct `/runs` execution;
- **Deferred** if the abstraction works but current workloads do not justify it;
- **Rejected** if it mostly wraps `RunAgent` without useful coordination or
  context semantics.

The governing rule remains:

> Complexity must earn its place.
