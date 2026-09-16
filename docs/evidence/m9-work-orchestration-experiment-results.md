# M9 Work API + Orchestrator V0 Experiment Results

- Status: Completed
- Date: 2026-09-16
- Milestone: M9 — Work API + Deterministic Orchestrator V0
- Governing principle: ADR-0002 — Evidence-Gated Architecture
- Related ADR: ADR-0007 — Work API and Deterministic Orchestrator V0
- Related capability: ADR-0006 — Evaluation Plane / Eval-as-Code
- Evaluated revision: `ba24a756ebb3ff23a689b9b66100b7841f25b700`

## Decision

**PROMOTE / ACCEPT**

The M9 experiment demonstrated reusable semantics above direct `RunAgent`
execution with a small deterministic orchestration boundary.

The accepted V0 provides:

```text
WorkRequest
    |
    +--> objective
    +--> explicit ContextRef[]
    +--> ordered WorkStep[]
    |
    v
WorkOrchestrator
    |
    v
RunAgent
    |
    v
RuntimeContract
```

and a separate contextual-recall path:

```text
explicit ContextRef[]
    |
    v
ContextualRecall
    |
    +--> one RetrievalQuery per selected namespace
    |
    v
RetrievalAcceptanceGate
    |
    +--> ACCEPT  -> usable hits
    +--> ABSTAIN -> no exposed hits
```

ADR-0007 may therefore be promoted from **Proposed** to **Accepted**.

This decision accepts only the behavior demonstrated by the experiment. It does
not accept an LLM planner, automatic Context Resolver, runtime prompt/context
injection, persistence, retries, parallelism, a queue, a workflow framework, or
distributed orchestration.

## Hypothesis

M9 tested whether a minimal deterministic Work abstraction could:

1. represent work separately from individual runs;
2. coordinate multiple ordered run steps through the existing `RunAgent`;
3. expose work-level lifecycle and results;
4. stop subsequent execution after the first failed run;
5. preserve completed run evidence after a later failure;
6. carry explicit shared/delivery/subject context references;
7. prevent unrelated memory namespaces from being queried implicitly;
8. remain independent from a model provider and runtime backend;
9. remain useful without an external workflow framework or persistent control
   plane;
10. produce structured deterministic evidence through the accepted M8
    Evaluation Plane.

The hypothesis was supported.

## Implemented V0 boundary

### Work contracts

M9 introduced the minimum work/context vocabulary:

```text
ContextRole
ContextRef
WorkStep
WorkRequest
WorkStatus
WorkStepResult
WorkResult
```

The accepted context roles are:

```text
shared
delivery
subject
```

No additional context-role taxonomy was required.

### Deterministic orchestration

The accepted execution policy is:

```text
for step in declared order:
    execute through RunAgent

    if run fails:
        stop

return WorkResult
```

The orchestrator does not execute runtimes directly and does not duplicate
`RuntimeContract`.

### Work API

The HTTP boundary is additive:

```text
POST /runs
POST /work
```

The existing `/runs` primitive remains available independently of the Work API.

### Explicit contextual recall

M9 also demonstrated an application-level contextual recall mechanism that:

- accepts only explicitly selected `ContextRef` values;
- issues one existing single-scope `RetrievalQuery` per selected namespace;
- preserves declared context order;
- reuses the M7 retrieval and acceptance contracts;
- exposes retrieved hits only when the corresponding acceptance decision is
  `ACCEPT`;
- performs no implicit global/all-namespace search.

The M7 `RetrievalQuery` contract did not require a multi-scope redesign.

## Evaluation workload 1 — Work orchestration

### Suite

```text
m9-work-v0
```

### Cases

```text
3
```

Coverage:

1. ordered multi-step success;
2. stop on first failure;
3. explicit subject-context switch.

### Result

```text
pass: 3
fail: 0
error: 0
deterministic_reproducibility: true
duration_seconds: 0.0011875659693032503
```

The duration value is recorded as experiment evidence only. It is not treated as
a formal performance benchmark.

### Evidence demonstrated

The suite proved:

- declared step order is preserved;
- successful work executes all declared steps;
- work-level status is distinct from individual run status;
- failure stops subsequent execution;
- the failed step is identified;
- completed step results remain available after failure;
- context references remain attached to the work result;
- the subject context can be switched explicitly while preserving shared and
  delivery contexts;
- repeated evaluation produces the same structured result.

## Evaluation workload 2 — Contextual recall

### Suite

```text
m9-contextual-recall-v0
```

### Cases

```text
4
```

Coverage:

1. LinkedIn delivery + Homelab subject;
2. LinkedIn delivery + Agent Platform subject;
3. no-evidence abstention;
4. no contexts -> no retrieval.

### Result

```text
pass: 4
fail: 0
error: 0
deterministic_reproducibility: true
duration_seconds: 0.024516110017430037
```

The duration value is recorded as experiment evidence only. It is not treated as
a formal performance benchmark.

### Evidence demonstrated

For:

```text
shared   -> global
delivery -> app:linkedin
subject  -> project:homelab
```

the observed queried namespaces were exactly:

```text
global
app:linkedin
project:homelab
```

For:

```text
shared   -> global
delivery -> app:linkedin
subject  -> project:agent-platform
```

the observed queried namespaces were exactly:

```text
global
app:linkedin
project:agent-platform
```

The suites demonstrated:

- context order correctness;
- exact namespace-selection correctness;
- zero unexpected namespace queries;
- accepted memory-ID correctness;
- explicit `ABSTAIN` with zero exposed memories;
- zero contexts causing zero retrievals;
- deterministic repeated execution.

## Aggregate result

Across both M9 evaluation suites:

```text
total cases: 7
pass: 7
fail: 0
error: 0
deterministic suites: 2 / 2
```

Machine-readable evidence:

```text
docs/evidence/artifacts/m9-work-v0.json
docs/evidence/artifacts/m9-contextual-recall-v0.json
```

## Success-criteria review

### 1. Work has identity/lifecycle separate from Run

**PASS**

`WorkResult` owns work identity and work status independently from the
`RunResult` values produced by individual steps.

### 2. Multiple ordered steps execute through one Work request

**PASS**

The work suite executed declared multi-step work and preserved exact step order.

### 3. RunAgent remains the execution primitive

**PASS**

`WorkOrchestrator` delegates each step to the existing `RunAgent` rather than
executing a runtime directly.

### 4. Stop-on-failure behavior is deterministic

**PASS**

The failure case executed the first and second steps, marked the second as the
failed step, and did not execute the third.

### 5. Completed step evidence survives a later failure

**PASS**

The successful first-step result and failed second-step result both remained in
the returned work result.

### 6. Context roles and namespaces remain explicit

**PASS**

`ContextRef` preserves both role and namespace. The experiment exercised shared,
delivery, and subject roles.

### 7. Legitimate cross-context composition is supported

**PASS**

The suites demonstrated both:

```text
global + app:linkedin + project:homelab
```

and:

```text
global + app:linkedin + project:agent-platform
```

without collapsing the contexts into one namespace.

### 8. Unselected contexts remain absent

**PASS**

Contextual recall recorded the exact queried namespace sequence and reported zero
unexpected queries.

No unrestricted all-memory search was required.

### 9. The Work API is additive and `/runs` remains available

**PASS**

The API exposes `/work` while retaining the existing `/runs` endpoint.

### 10. The core remains provider/runtime independent

**PASS**

`WorkOrchestrator` coordinates `RunAgent` and does not depend on a model
provider. Evaluation used a deterministic runtime without changing orchestration
contracts.

### 11. No external workflow framework, queue, or persistent store is required

**PASS**

V0 remained synchronous and in-process.

The experiment required no Temporal, Celery, Airflow, Kafka, RabbitMQ, scheduler,
broker, durable workflow engine, or work database.

### 12. M8 Eval-as-Code produces structured orchestration evidence

**PASS**

Both M9 evaluators reused the accepted evaluation core and emitted versioned JSON
artifacts with PASS / FAIL / ERROR summaries and deterministic-reproducibility
evidence.

## Guardrail review

M9 did not:

- replace `RunAgent`;
- duplicate `RuntimeContract`;
- turn the orchestrator into an agent;
- add an LLM planner;
- infer memory contexts automatically;
- search all memory namespaces by default;
- add retries;
- add parallel step execution;
- add DAG scheduling;
- add work persistence;
- add a queue or broker;
- add distributed workers;
- add an external workflow framework;
- make evaluation responsible for architectural promotion.

## Deviations and clarifications

### No separate WorkPlan type

The initial ADR showed a conceptual `WorkPlan`, but the experiment did not
demonstrate a need for separate plan identity or lifecycle.

The ordered `WorkStep` values inside `WorkRequest` were sufficient for V0.

This is consistent with the evidence-gated rule that a separate `WorkPlan`
abstraction should only be introduced when it earns its place.

### Contextual recall remained separate from runtime context injection

M9 proved explicit context composition, context-scoped recall, acceptance, and
absence of implicit unrelated-context retrieval.

It did **not** inject recalled memories into `RunRequest`, `RuntimeRequest`, or a
model prompt.

That remains a separate capability because:

```text
Memory != Retrieval != Context Injection
```

Accepting ADR-0007 therefore does not imply that context injection has been
implemented or accepted.

### Work-level observability was not expanded

Existing run-level observability continued to be reused.

The experiment did not demonstrate a need to add dedicated `work.started`,
`work.succeeded`, or `work.failed` telemetry before accepting the minimal
orchestration boundary.

Work-level observability remains a future evidence-gated enhancement.

## What was learned

### Work is useful above Run

The Work abstraction adds real semantics rather than merely renaming a run:

- ordered multi-step coordination;
- work-level outcome;
- stop-on-failure policy;
- completed-step aggregation;
- explicit context intent.

### Planning did not need to become intelligent

The experiment confirmed:

```text
Planning != Orchestration
```

A deterministic caller-supplied step list was sufficient to prove the
orchestration boundary.

### Context selection can remain explicit

No automatic Context Resolver was required to demonstrate legitimate
cross-context work.

Explicit context selection is auditable and deterministic, and it provides a
useful baseline against which any future automatic resolver can be evaluated.

### The existing single-scope retrieval contract remains sufficient

Multi-context behavior was achieved by composing one existing retrieval operation
per explicitly selected scope.

No multi-scope retrieval primitive or cross-scope BM25 ranking mechanism was
needed.

## Accepted V0 boundary

M9 accepts:

```text
WorkRequest
WorkStep
WorkStatus
WorkStepResult
WorkResult
ContextRole
ContextRef
WorkOrchestrator
POST /work
ContextualRecall
WorkEvaluator
ContextualRecallEvaluator
version-controlled M9 eval datasets
machine-readable M9 evidence artifacts
```

The accepted orchestration policy is:

```text
synchronous
in-process
ordered
sequential
stop on first failure
preserve completed results
explicit context selection
```

## Explicitly deferred

The following are not accepted as required M9 V0 architecture:

- LLM plan generation;
- automatic Context Resolver;
- automatic context inference;
- runtime/model context injection;
- automatic output-to-input step interpolation;
- global cross-context retrieval;
- cross-scope ranking;
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
- external orchestration framework;
- dedicated work-level observability events.

Each remains evidence-gated.

## Final conclusion

The Work API and deterministic orchestration boundary earned their place.

M9 demonstrated useful semantics above direct run execution, explicit and
auditable context composition, deterministic failure behavior, and reusable
Eval-as-Code evidence without introducing a workflow framework or automatic
planner.

ADR-0007 should therefore be marked **Accepted**.

The governing principle remains:

> Complexity must earn its place.
