# ADR-0006: Evaluation Plane / Eval-as-Code

- Status: Proposed
- Date: 2026-09-15
- Governing principle: ADR-0002 — Evidence-Gated Architecture

## Trigger

The Agent Platform already requires evidence before material architectural
changes are accepted.

That process has been successfully applied to:

- persistent deployment;
- trusted self-development boundaries;
- local model inference;
- Memory & Recall;
- retrieval acceptance behavior.

However, evaluation is still mostly implemented through a combination of:

- unit tests;
- smoke scripts;
- manual experiment procedures;
- Markdown evidence;
- operator interpretation.

This works, but the platform currently lacks a reusable mechanism for expressing
evaluation cases and producing structured quality evidence.

## Principle

Evaluation is a distinct concern.

```text
Eval != Observability != Benchmark != Test != Guardrail
```

### Observability

Observability records what happened.

Examples:

- logs;
- traces;
- metrics;
- lifecycle events;
- token usage;
- latency.

### Evaluation

Evaluation determines how well a result satisfied an expected objective.

Examples:

- whether a relevant memory was recalled;
- whether an irrelevant query correctly abstained;
- whether a tool trajectory completed successfully;
- whether a generated artifact met acceptance criteria.

### Benchmark

Benchmarking compares implementations, models, providers or configurations under
controlled conditions.

### Test

Tests verify implementation invariants and expected program behavior.

### Guardrail

Guardrails prevent or block prohibited behavior.

Evaluation may later inform promotion policy, but it is not itself a runtime
guardrail.

## Current baseline

The baseline is documentation-first evidence collection under ADR-0002.

The current process is valid and remains authoritative while M8 is experimental.

There is no accepted Evaluation Plane yet.

## Proposed decision

Introduce an experimental, provider-agnostic Evaluation Plane based on
Eval-as-Code.

The proposal is:

```text
Target execution
      |
      v
Observed result
      |
      v
EvaluationContract
      |
      v
Eval Runner
      |
      v
EvaluationResult
      |
      +--> outcome
      +--> metrics
      +--> reason_code
      +--> metadata
```

The plane must remain independent from the runtime, model provider, retrieval
backend and tool protocol being evaluated.

## Proposed core concepts

The minimum domain should contain equivalents of:

```text
EvaluationCase
EvaluationResult
EvaluationOutcome
EvaluationMetric
EvaluationContract
```

A runner may coordinate execution, but the runner itself must not become the
definition of evaluation semantics.

Evaluation semantics belong to the evaluator.

## Initial outcome model

The initial outcome vocabulary should remain intentionally small:

```text
PASS
FAIL
ERROR
```

Continuous scores may be included as metrics when needed, but a universal
0-to-1 quality score is explicitly not required.

Different evaluation types may require different metrics.

## First implementation target

The first evaluator should target M7 Memory & Recall.

Why:

- behavior is deterministic;
- expected results can be labeled explicitly;
- ACCEPT and ABSTAIN are already first-class outcomes;
- retrieval ranking can be measured;
- the workload does not require subjective language judging;
- the existing platform contracts provide a clean integration boundary.

Example:

```text
EvaluationCase
  query: local inference
  namespace: agent
  expected_decision: ACCEPT
  expected_memory: memory-123
```

Execution:

```text
case
  |
  v
RetrievalContract
  |
  v
Retrieval Acceptance Gate
  |
  v
actual result
  |
  v
Retrieval evaluator
  |
  v
PASS / FAIL + metrics
```

## Eval Runner responsibilities

The proposed Eval Runner may:

- execute evaluation cases;
- invoke the relevant evaluator;
- collect structured results;
- aggregate deterministic metrics;
- correlate results with experiment identifiers;
- emit a reproducible report.

It should not:

- select architecture automatically;
- mutate production configuration;
- promote a candidate automatically;
- become a general workflow orchestrator;
- require a persistent service;
- require LLM-based judgment for deterministic cases.

## Deterministic evals first

M8 begins with deterministic code-based evaluators.

Examples:

```text
exact outcome match
expected tool invoked
expected memory present
expected memory absent
expected ACCEPT / ABSTAIN
rank threshold
schema validity
artifact invariant
```

These are preferred because they are:

- reproducible;
- explainable;
- inexpensive;
- independent from another model provider.

## Retrieval evals

The first supported evaluation family should measure retrieval behavior.

Candidate metrics include:

- recall@k;
- precision@k;
- top-1 correctness;
- ACCEPT correctness;
- ABSTAIN correctness;
- false-positive recalls;
- false-negative recalls;
- deterministic reproducibility;
- latency.

Metric selection must remain workload-specific.

The platform must not pretend that one aggregate score captures all retrieval
quality.

## Agent and trajectory evals

Agent / trajectory evaluation is a later extension.

Potential future evaluations include:

- task completed;
- required tools used;
- forbidden tools not used;
- retry count;
- successful verification;
- acceptance criteria satisfied;
- budget respected.

These do not enter M8 V0 automatically.

## LLM-as-Judge

LLM-as-Judge is explicitly deferred.

It may be evaluated later for outputs that cannot be judged deterministically.

If introduced, it must remain behind an evaluator/provider boundary and must be
measured against:

- deterministic alternatives;
- human-labeled cases;
- consistency;
- cost;
- latency;
- judge-model sensitivity.

LLM-as-Judge must not become a hidden authority over architectural promotion.

## Benchmarking relationship

Evaluation measures a target.

Benchmarking compares targets.

Conceptually:

```text
Baseline
   |
   v
Eval Suite
   |
   v
Baseline Results

Candidate
   |
   v
Same Eval Suite
   |
   v
Candidate Results

Baseline Results
        |
        +----> Comparison ----> Evidence
        |
Candidate Results
```

Comparison must use predefined success metrics and guardrails.

A candidate is not accepted merely because one metric improves.

## Promotion relationship

If M8 is accepted, the intended architecture workflow becomes:

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

Promotion remains a policy / human-governance concern.

The Eval Plane supplies evidence.

It does not own architectural authority.

## Provider independence

The Evaluation Plane must not depend structurally on:

- OpenAI;
- OpenRouter;
- local inference;
- DSH;
- MCP;
- SQLite;
- a specific eval SaaS;
- a specific orchestration framework.

Adapters may integrate external evaluation providers later if evidence requires
them.

## Persistence

M8 V0 does not require a dedicated evaluation database.

Evaluation results may initially be:

- returned in memory;
- serialized as JSON;
- written as experiment artifacts;
- committed as Markdown evidence when appropriate.

A persistent eval store is deferred until a requirement demonstrates that it is
necessary.

## Observability

Evaluation execution itself may emit normal platform observability:

- eval run started;
- eval run completed;
- eval run failed;
- case count;
- duration;
- evaluator identifier.

Sensitive evaluated content should not be copied into logs or metrics by
default.

Evaluation results and observability remain separate.

## Success criteria

The Evaluation Plane may be accepted only if the M8 experiment proves:

1. evaluation cases can be represented as reusable data;
2. deterministic evaluators produce structured reproducible results;
3. the same runner can execute multiple cases without bespoke orchestration;
4. retrieval evaluation can measure accepted M7 behavior;
5. negative / abstention behavior can be evaluated explicitly;
6. the evaluation abstraction does not leak SQLite or retrieval implementation
   details into core contracts;
7. the mechanism reduces manual experiment work;
8. a second evaluation type can reuse the same core abstractions without
   redesign;
9. no persistent control plane or external eval framework is required for V0;
10. results can support baseline-vs-candidate evidence later.

## Guardrails

M8 must not:

- replace unit tests;
- replace observability;
- turn evaluation into runtime authorization;
- auto-promote architecture changes;
- require LLM-as-Judge for deterministic workloads;
- introduce a mandatory external eval provider;
- add a dedicated eval database without evidence;
- couple evaluation contracts to a specific model, runtime, tool or retrieval
  backend;
- expose sensitive prompts, memory content, tool arguments or model outputs in
  default telemetry.

## Alternatives

### Keep the current manual process

This remains the baseline.

It is acceptable if the M8 experiment does not demonstrate enough value.

### Adopt an external eval framework immediately

Deferred.

Examples may include general-purpose LLM evaluation frameworks or hosted eval
platforms.

No requirement currently proves that the platform needs one.

### Implement a minimal internal Eval Runner

Proposed experiment.

This is the smallest candidate capable of testing whether reusable Eval-as-Code
provides measurable value.

## Consequences if accepted

### Positive

- architecture experiments become more reproducible;
- evaluation cases become reusable;
- baseline and candidate comparisons become easier;
- quality evidence becomes machine-readable;
- retrieval, model, tool and agent experiments can converge on shared
  evaluation concepts;
- ADR-0002 becomes easier to operationalize.

### Negative

- a new platform abstraction is introduced;
- evaluation contracts require maintenance;
- poor metric design can create false confidence;
- evaluation suites can become stale;
- future LLM-based evaluators may introduce cost and nondeterminism.

## Experiment

This ADR remains **Proposed** until the experiment defined in:

```text
docs/evidence/m8-eval-experiment-plan.md
```

is completed.

The experiment must produce:

```text
docs/evidence/m8-eval-experiment-results.md
```

## Decision rule

After the experiment:

- **Accepted** if the evaluation abstraction demonstrates reusable and
  reproducible value;
- **Deferred** if useful but not yet justified as a platform plane;
- **Rejected** if it mainly duplicates tests or manual evidence without enough
  benefit.

Until then, the current documentation-first evidence process remains the
accepted baseline.

## Re-evaluation triggers

Even if the initial proposal is Deferred or Rejected, evaluation infrastructure
may be reconsidered when:

- repeated experiments duplicate the same evaluation logic;
- retrieval candidates require standardized comparison;
- multiple model providers require task-quality comparison;
- sandbox/runtime candidates require semantic-invariance evaluation;
- agent trajectories require repeatable acceptance measurement;
- manual evidence interpretation becomes a material bottleneck.
