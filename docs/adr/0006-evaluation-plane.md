# ADR-0006: Evaluation Plane / Eval-as-Code

- Status: Accepted
- Proposed: 2026-09-15
- Accepted: 2026-09-16
- Governing principle: ADR-0002 — Evidence-Gated Architecture
- Evidence: `docs/evidence/m8-eval-experiment-results.md`

## Context

The Agent Platform requires evidence before material architectural complexity is
accepted.

Before M8, evaluation evidence was produced through a combination of:

- unit tests;
- smoke scripts;
- manual experiment procedures;
- Markdown evidence;
- operator interpretation.

That process worked, but repeated experiments lacked a small shared mechanism for
representing labeled evaluation cases and emitting structured quality evidence.

M7 Memory & Recall created a suitable deterministic workload for testing whether
a reusable Evaluation Plane could provide enough value to justify a new platform
abstraction.

## Decision

Accept a minimal, provider-agnostic **Evaluation Plane / Eval-as-Code**.

The accepted V0 is:

```text
EvaluationCase
      |
      v
EvalRunner
      |
      v
EvaluationContract
      |
      v
capability-specific evaluator
      |
      v
EvaluationResult
```

The Evaluation Plane is responsible for executing reusable evaluation cases and
producing structured evidence about whether observed capability behavior
satisfied explicit expectations.

It does not own architectural promotion.

## Core principle

```text
Eval != Observability != Benchmark != Test != Guardrail
```

### Evaluation

Determines how well a capability result satisfied defined expectations.

### Observability

Records what happened during execution.

### Benchmark

Compares alternatives under controlled conditions.

### Test

Verifies implementation invariants and expected program behavior.

### Guardrail

Prevents or blocks prohibited runtime behavior.

These concerns may exchange evidence, but they remain distinct.

## Accepted core concepts

### EvaluationCase

A reusable, data-oriented representation of:

- case identity;
- input;
- expected behavior;
- metadata.

The core case remains generic. Capability-specific validation belongs to the
evaluator.

### EvaluationOutcome

The accepted V0 vocabulary is intentionally small:

```text
PASS
FAIL
ERROR
```

No universal quality score is required.

### EvaluationResult

A structured result containing:

- case ID;
- evaluator identity;
- outcome;
- reason code;
- finite numeric metrics;
- metadata.

### EvaluationContract

The boundary implemented by capability-specific evaluators.

Evaluation semantics belong to the evaluator rather than the runner.

### EvalRunner

The application-layer coordinator responsible for:

- executing cases;
- invoking an evaluator;
- preserving case order;
- collecting results;
- converting evaluator exceptions into ERROR results;
- summarizing PASS / FAIL / ERROR outcomes.

The runner is not a general workflow orchestrator.

## Why this is accepted

The M8 experiment demonstrated reusable value across two independent platform
capabilities.

### Retrieval evaluation

The first evaluator exercised the accepted M7 stack through platform-owned
interfaces:

```text
SQLiteMemoryStore
    |
    v
SQLiteFTSRetrieval
    |
    v
LexicalRetrievalAcceptanceGate
    |
    v
RetrievalEvaluator
```

A real labeled suite validated:

- expected ACCEPT behavior;
- expected ABSTAIN behavior;
- expected memory recall;
- top-1 correctness;
- scope isolation;
- repeated-run determinism.

Result:

```text
suite: m8-retrieval-v0
cases: 4
pass: 4
fail: 0
error: 0
deterministic_reproducibility: true
```

### Tool capability evaluation

A second evaluator exercised the existing tool boundary and the real
`DiagnosticEchoTool`.

It validated:

- successful invocation;
- expected output values;
- run_id preservation;
- tool-name preservation;
- expected validation failure;
- repeated-run determinism.

Result:

```text
suite: m8-tool-v0
cases: 3
pass: 3
fail: 0
error: 0
deterministic_reproducibility: true
```

The second capability reused the same evaluation core without redesign.

That is the primary evidence that the abstraction is not retrieval-specific.

## Provider and subsystem independence

The evaluation core must not depend structurally on:

- OpenAI;
- OpenRouter;
- local inference;
- DSH;
- MCP;
- SQLite;
- a specific runtime;
- a specific tool implementation;
- a specific retrieval backend;
- a specific evaluation SaaS.

Capability-specific evaluators may depend on the contracts required to evaluate
their target.

Those dependencies must remain outside the generic evaluation core.

## Deterministic evaluation first

Deterministic code-based evaluators are the accepted default for workloads where
expected behavior can be expressed without subjective judgment.

Examples include:

- exact outcome matching;
- expected ACCEPT / ABSTAIN;
- expected memory presence;
- rank correctness;
- schema validity;
- expected tool success;
- expected tool failure;
- output invariants;
- runtime contract invariants.

This approach is preferred because it is:

- reproducible;
- explainable;
- inexpensive;
- fast;
- independent from another model provider.

## Workload-specific metrics

Metrics belong to the evaluation workload.

Examples already demonstrated include:

### Retrieval

- decision match;
- hit count;
- expected-memory recall@k;
- top-1 correctness.

### Tool capability

- invocation success;
- run_id match;
- tool-name match;
- output match;
- expected-error match.

The platform must not collapse these into a universal aggregate quality score
without evidence that such a score is useful and valid.

## Evaluation data

Evaluation cases may be stored as version-controlled data.

The accepted V0 uses JSON datasets for deterministic suites.

This makes cases:

- reviewable;
- repeatable;
- diffable;
- reusable across runs.

A dedicated evaluation database is not required.

## Evaluation artifacts

Evaluation results may be:

- returned in memory;
- serialized as JSON;
- persisted as experiment artifacts;
- summarized as Markdown evidence.

The accepted M8 evidence includes:

```text
docs/evidence/artifacts/m8-retrieval-v0.json
docs/evidence/artifacts/m8-tool-v0.json
docs/evidence/m8-eval-experiment-results.md
```

## Relationship to Evidence-Gated Architecture

The Evaluation Plane operationalizes part of ADR-0002.

The intended workflow is:

```text
CHANGE
  |
  v
EXPERIMENT
  |
  v
EVALUATE
  |
  v
COMPARE BASELINE
  |
  v
EVIDENCE
  |
  +--> PROMOTE
  |
  +--> REJECT / DEFER
```

Evaluation produces evidence.

Promotion remains an explicit architecture / policy decision.

An evaluator must never silently promote a candidate into production.

## Relationship to benchmarking

Evaluation measures a target.

Benchmarking compares targets.

A future baseline-vs-candidate workflow may run the same evaluation suite against
multiple implementations and compare the resulting evidence.

M8 does not introduce a generic comparison abstraction because no concrete
candidate comparison required one.

Any future comparison layer must earn its place independently.

## Relationship to observability

Evaluation execution may emit normal platform observability such as:

- evaluation started;
- evaluation completed;
- evaluation failed;
- evaluator identity;
- case count;
- duration.

Evaluation results and observability remain distinct.

Sensitive evaluated inputs or outputs must not be copied into default telemetry
without a justified requirement.

## Relationship to tests

Evaluation does not replace tests.

Tests verify software invariants.

Eval suites represent reusable labeled capability expectations and produce
structured evidence.

Some overlap in low-level assertions is acceptable when it supports different
purposes, but duplication must remain justified.

## Error semantics

V0 distinguishes:

```text
FAIL
```

The evaluator executed correctly, but observed behavior did not satisfy the
expected behavior.

```text
ERROR
```

The evaluation itself could not be completed correctly, for example because of
invalid case data or evaluator failure.

This distinction is part of the accepted evaluation contract.

## Guardrails

The Evaluation Plane must not:

- replace unit tests;
- replace observability;
- become runtime authorization;
- automatically select architecture;
- automatically mutate production configuration;
- automatically promote candidates;
- require LLM-as-Judge for deterministic workloads;
- require a mandatory external evaluation provider;
- require a dedicated evaluation database without evidence;
- expose sensitive prompts, memory content, tool arguments, or model outputs in
  default telemetry;
- couple the generic evaluation domain to a specific model, runtime, tool,
  retrieval backend, or provider.

## LLM-as-Judge

LLM-as-Judge remains explicitly deferred.

It may be evaluated later for outputs that cannot be judged deterministically.

If introduced, it must remain behind an evaluator/provider boundary and must
itself be evaluated for:

- agreement with deterministic or human labels;
- consistency;
- cost;
- latency;
- judge-model sensitivity;
- failure modes.

LLM-as-Judge must never become a hidden authority over architectural promotion.

## Persistent evaluation infrastructure

A persistent evaluation service or dedicated eval database is not part of V0.

The current evidence demonstrates sufficient value using:

```text
plain Python
+ Pydantic
+ existing platform contracts
+ deterministic evaluators
+ version-controlled datasets
+ JSON artifacts
```

Persistent infrastructure may be reconsidered only when a concrete requirement
demonstrates that the current approach is insufficient.

## Agent and trajectory evaluation

Agent and trajectory evaluation is a future extension.

Potential future cases include:

- task completed;
- required tools used;
- forbidden tools not used;
- retry count within budget;
- verification succeeded;
- acceptance criteria satisfied;
- resource or token budget respected.

These capabilities are not automatically accepted by this ADR.

They must be introduced incrementally and remain evidence-gated.

## Consequences

### Positive

- evaluation cases become reusable;
- evidence becomes machine-readable;
- repeated experiments become easier to reproduce;
- capability quality can be checked separately from implementation tests;
- future baseline/candidate comparisons can reuse structured results;
- multiple platform capabilities can converge on shared evaluation concepts;
- ADR-0002 gains an executable evidence mechanism.

### Negative

- the platform now owns an additional abstraction;
- evaluation contracts require maintenance;
- poor labels or metrics can create false confidence;
- evaluation datasets can become stale;
- future subjective evaluators may introduce cost and nondeterminism.

These costs are accepted because the M8 experiment demonstrated concrete reuse
across independent capabilities with a small implementation.

## Evidence

The acceptance decision is grounded in:

```text
docs/evidence/m8-eval-experiment-plan.md
docs/evidence/m8-eval-experiment-results.md
docs/evidence/artifacts/m8-retrieval-v0.json
docs/evidence/artifacts/m8-tool-v0.json
```

Evaluated revision:

```text
8e8051e465a9feafaf57f01d644466b989963961
```

Aggregate result:

```text
7 cases
7 PASS
0 FAIL
0 ERROR
2 / 2 deterministic suites
```

## Explicitly deferred

This ADR does not accept the following as required architecture:

- LLM-as-Judge;
- external eval frameworks or SaaS;
- persistent eval service;
- dedicated eval database;
- distributed evaluation workers;
- generic comparison engine;
- universal quality score;
- agent trajectory scoring;
- human preference collection;
- automatic promotion;
- evaluation dashboard UI.

## Re-evaluation triggers

The Evaluation Plane should be revisited when:

- model/provider comparisons require task-quality evidence;
- retrieval candidates require standardized baseline comparison;
- sandbox/runtime candidates require semantic-invariance evaluation;
- agent trajectories require repeatable task-success measurement;
- evaluation datasets become large enough to require dedicated storage;
- subjective outputs create a justified need for human or LLM-based judges;
- manual interpretation of evaluation artifacts becomes a material bottleneck.

## Final decision

The Evaluation Plane has demonstrated enough reusable and reproducible value to
earn a place in the Agent Platform architecture.

ADR-0006 is therefore **Accepted**.

The governing rule remains unchanged:

> Complexity must earn its place.
