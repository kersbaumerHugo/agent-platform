# M9 Work API + Orchestrator V0 Experiment Plan

- Status: Completed
- Date: 2026-09-16
- Governing principle: ADR-0002 — Evidence-Gated Architecture
- Related ADR: ADR-0007 — Work API and Deterministic Orchestrator V0
- Related capability: ADR-0006 — Evaluation Plane / Eval-as-Code
- Result: Accepted
- Results: `docs/evidence/m9-work-orchestration-experiment-results.md`

## Objective

Test whether a minimal Work abstraction and deterministic Orchestrator can
coordinate user-level multi-step work above the existing `RunAgent` boundary
without introducing a workflow framework, persistent control plane, automatic
planner, queue, or distributed execution system.

The experiment must also prove that explicit multi-context intent can be carried
through work orchestration without allowing unrestricted memory-context access.

## Current baseline

The current execution path is:

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

This is a valid low-level execution primitive.

The baseline does not provide:

- work-level identity/state;
- multiple ordered execution steps;
- stop-on-failure sequencing;
- work-level aggregation of run results;
- explicit delivery/subject/shared context composition.

## Hypothesis

A minimal deterministic WorkOrchestrator can add useful coordination by:

1. representing work separately from individual runs;
2. executing multiple ordered steps through the existing `RunAgent`;
3. preserving work-level state;
4. stopping later steps after a failure;
5. preserving completed step evidence;
6. carrying explicit context references across execution;
7. remaining independent from model/runtime providers;
8. remaining small enough that no external orchestration framework is required.

If the implementation merely wraps a single run without adding useful semantics,
ADR-0007 should remain Deferred or be Rejected.

## Architectural distinctions

The experiment must preserve:

```text
Work != Plan != Run != Orchestrator != Runtime != Agent
```

It must also preserve:

```text
Planning != Orchestration
```

M9 V0 coordinates an explicit plan.

It does not require an LLM to generate that plan.

## Context requirement

The experiment incorporates the contextual-memory requirement discovered before
M9.

A work item may compose multiple explicit contexts.

Example:

```text
Write LinkedIn post about homelab

shared:
  global

delivery:
  app:linkedin

subject:
  project:homelab
```

The experiment must prove that:

- all selected contexts survive orchestration;
- context roles remain distinguishable;
- unrelated contexts are not silently added;
- cross-context composition is allowed only through explicit selection.

M9 does not need to implement automatic memory retrieval across these contexts.

The immediate goal is to establish and validate the work-level context contract.

## Proposed minimum domain

The experiment may introduce equivalents of:

```text
ContextRole
ContextRef
WorkStep
WorkRequest
WorkStatus
WorkResult
```

The initial roles should be limited to demonstrated needs:

```text
shared
delivery
subject
```

Do not add additional role taxonomies without a real case.

## Proposed request shape

Conceptually:

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
  ],
  "steps": [
    {
      "step_id": "draft",
      "agent_id": "writer",
      "input": "Draft the post"
    },
    {
      "step_id": "review",
      "agent_id": "reviewer",
      "input": "Review the draft"
    }
  ]
}
```

The actual V0 may keep step input independent rather than implementing
cross-step interpolation.

Automatic output-to-input templating is not required.

## Execution policy

V0 policy:

```text
for step in declared order:
    execute step through RunAgent

    if step fails:
        stop

return WorkResult
```

The orchestrator should not duplicate runtime behavior already implemented by
`RunAgent`.

## First implementation sequence

### M9.0 — Baseline and experiment plan

- define Work / Run distinction;
- define deterministic V0 policy;
- define explicit context-composition requirement;
- define guardrails and success criteria.

### M9.1 — Work domain contracts

Introduce only the minimal work/context data models.

No API or orchestration engine should be added before the contracts pass their
own validation tests.

### M9.2 — Deterministic WorkOrchestrator

Implement sequential execution over existing `RunAgent`.

Required behavior:

- preserve declared order;
- aggregate run results;
- stop on first failed run;
- return work-level status.

### M9.3 — Work API

Expose the orchestration boundary through FastAPI while preserving `/runs`.

The API should remain synchronous for V0.

### M9.4 — Explicit context propagation

Prove that:

```text
shared + delivery + subject
```

context references enter the work request and remain available throughout the
work result/execution path.

No automatic scope inference enters this phase.

### M9.5 — Eval-as-Code

Use ADR-0006 to build deterministic work/orchestration evaluation cases.

Required cases:

```text
single step succeeds
multiple steps preserve order
failure stops later steps
completed results survive work failure
multiple context roles are preserved
unselected contexts are absent
```

### M9.6 — Evidence and ADR decision

Capture:

- exact Git revision;
- test/eval results;
- orchestration cases;
- work/run behavior;
- context propagation evidence;
- implementation complexity;
- whether external orchestration infrastructure was required.

Then decide:

```text
Accepted
Deferred
Rejected
```

## Initial evaluation cases

### Case 1 — Single-step success

```text
Work
  -> step A succeeds
  -> Work SUCCEEDED
```

Expected:

- one run result;
- work succeeds;
- step identity preserved.

### Case 2 — Ordered multi-step success

```text
A -> B -> C
```

Expected:

- A executes before B;
- B executes before C;
- all results are preserved;
- work succeeds.

### Case 3 — Stop on failure

```text
A succeeds
B fails
C exists
```

Expected:

- A result preserved;
- B failure preserved;
- C never executes;
- work fails.

### Case 4 — Context composition

Selected:

```text
shared: global
delivery: app:linkedin
subject: project:homelab
```

Expected:

- all three references preserved;
- roles preserved;
- no unrelated context appears.

### Case 5 — Different subject, same delivery

Selected:

```text
shared: global
delivery: app:linkedin
subject: project:agent-platform
```

Expected:

- LinkedIn delivery context remains;
- Agent Platform subject context is selected;
- homelab context is absent.

This case directly models legitimate cross-context LinkedIn work.

## Metrics

The first orchestration eval should remain simple.

Candidate metrics:

- work success correctness;
- executed-step count;
- expected-step-order correctness;
- stop-on-failure correctness;
- completed-result preservation;
- context-selection correctness;
- unexpected-context count;
- deterministic reproducibility;
- work duration.

Do not create a universal orchestration quality score.

## Persistence

M9 V0 should remain in-memory and synchronous unless the experiment discovers a
restart/resume requirement.

A persistent work store is explicitly deferred.

This means a process restart may lose in-flight work in V0.

That limitation is acceptable for the experiment and must be documented rather
than hidden.

## API compatibility

Existing:

```text
POST /runs
```

must continue to work.

The new Work API is additive.

The experiment should not force existing callers through WorkOrchestrator.

## Observability

Reuse the existing observability system.

At minimum, consider work-level events for:

```text
work.started
work.succeeded
work.failed
```

Do not log full work inputs, memory content, or context payloads by default.

## Success criteria

M9 succeeds only if all of the following are demonstrated:

1. Work has a useful identity/lifecycle separate from Run.
2. Multiple ordered steps can execute through one Work request.
3. RunAgent remains the execution primitive.
4. Stop-on-failure behavior is deterministic.
5. Completed step evidence is retained after a later failure.
6. Context roles and namespaces remain explicit.
7. Legitimate cross-context composition is supported.
8. Unselected contexts remain absent.
9. The Work API is additive and does not break `/runs`.
10. The core remains provider/runtime independent.
11. No external workflow framework, queue, or persistent store is required.
12. M8 Eval-as-Code can produce structured evidence about orchestration behavior.

## Guardrails

Do not introduce during M9 V0:

```text
LLM planner
automatic Context Resolver
implicit all-memory search
DAG engine
parallel execution
automatic retries
workflow compensation
persistent queue
broker
distributed workers
scheduler
Temporal
Celery
Airflow
Kafka
RabbitMQ
Kubernetes orchestration
human approval engine
workflow UI
```

Any future addition requires a concrete trigger and evidence.

## Decision rule

### Accept

Accept ADR-0007 if Work + Orchestrator demonstrates reusable semantics above
`RunAgent`, including deterministic multi-step coordination and explicit context
composition.

### Defer

Defer if the abstraction works but current workloads are still effectively
single-run and context propagation adds little value.

### Reject

Reject if WorkOrchestrator mostly forwards to `RunAgent` and creates additional
domain/API surface without useful coordination.

## Expected value

If successful, M9 establishes:

```text
user intent
    |
    v
Work API
    |
    v
explicit context + explicit plan
    |
    v
WorkOrchestrator
    |
    v
RunAgent
    |
    v
Runtime
```

This provides a stable boundary where future capabilities may later plug in:

```text
planner
Context Resolver
durable execution
sandbox selection
policy
human approval
distributed orchestration
```

without requiring them in V0.

The goal of M9 is not to build a workflow platform.

The goal is to prove the smallest useful work-orchestration boundary.
