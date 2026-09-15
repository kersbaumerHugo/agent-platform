# M8 Eval-as-Code Experiment Plan

- Status: Proposed experiment
- Date: 2026-09-15
- Governing principle: ADR-0002 — Evidence-Gated Architecture
- Related milestone: M8 — Evaluation Plane / Eval-as-Code

## Objective

Test whether a minimal, deterministic evaluation mechanism can convert the
Agent Platform's currently manual evidence process into reproducible,
machine-executable evaluations without introducing a heavyweight eval framework,
LLM-as-Judge dependency, external service, or new control plane.

The experiment must demonstrate value before an Evaluation Plane is accepted as
platform architecture.

## Architectural separation

The experiment adopts the following distinction:

```text
Eval != Observability != Benchmark != Test != Guardrail
```

Definitions:

- **Observability** records what happened during execution.
- **Eval** determines how well a result satisfied defined expectations.
- **Benchmark** compares alternatives under controlled conditions.
- **Test** verifies invariants and expected program behavior.
- **Guardrail** prevents or blocks prohibited behavior.
- **Eval** produces evidence about outcome quality or task success.

The experiment must not collapse these concerns into one abstraction.

## Current baseline

Today the platform already follows an evidence-gated workflow, but evaluation is
primarily manual.

Examples include:

- deployment experiments recorded as Markdown evidence;
- manual comparison of baseline and candidate behavior;
- manual inspection of retrieval ACCEPT / ABSTAIN behavior;
- manual validation of persistence, scope isolation, recovery and rollout;
- tests that verify implementation invariants but do not produce reusable
  evaluation results.

The current process is effective but has limitations:

- evaluation cases are not represented as reusable data;
- results are not emitted through a common evaluation contract;
- baseline and candidate runs are not compared through a common mechanism;
- repeated architecture experiments require bespoke scripts and interpretation;
- evaluation evidence is harder to aggregate across components.

## Trigger

M7 Memory & Recall introduced a deterministic, testable capability with clear
quality expectations:

```text
query
  -> retrieval
  -> acceptance decision
  -> recalled memories or abstention
```

This provides a suitable first workload for testing Eval-as-Code without
starting with subjective model-output evaluation.

## Hypothesis

A minimal deterministic Eval Runner with platform-owned evaluation contracts can:

1. execute reusable evaluation cases;
2. produce structured PASS / FAIL outcomes and measurements;
3. evaluate the M7 lexical retrieval baseline reproducibly;
4. support baseline-vs-candidate comparison later;
5. reduce manual evaluation effort;
6. remain independent from specific eval frameworks and LLM providers.

If those benefits are not demonstrated, the Evaluation Plane should remain
Deferred.

## Experiment scope

The first experiment evaluates only deterministic Memory & Recall behavior.

Initial evaluation cases should cover:

```text
relevant query
  -> expected ACCEPT
  -> expected memory present

unrelated query
  -> expected ABSTAIN

wrong scope
  -> expected ABSTAIN

fixed corpus + fixed query
  -> deterministic ranking
```

The experiment does not require:

```text
LLM-as-Judge
agent trajectory scoring
semantic similarity
embeddings
external eval platforms
human preference collection
distributed evaluation workers
persistent eval service
dashboard UI
```

## Proposed minimum domain

The experiment may introduce equivalents of:

```text
EvaluationCase
EvaluationResult
EvaluationMetric
EvaluationOutcome
EvaluationContract
EvalRunner
```

The initial outcome vocabulary should remain small:

```text
PASS
FAIL
ERROR
```

A richer score model must not be added unless a concrete evaluation requires it.

## Proposed execution flow

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
Target capability
      |
      v
Observed result
      |
      v
Deterministic evaluator
      |
      v
EvaluationResult
      |
      +--> outcome
      +--> metrics
      +--> reason_code
      +--> metadata
```

## First evaluation target — M7 Retrieval

The first evaluator should assess the accepted lexical retrieval baseline:

```text
SQLite FTS5/BM25
        |
        v
Retrieval Acceptance Gate
        |
        v
ACCEPT / ABSTAIN
```

Example case shape:

```text
case_id
namespace
query
expected_decision
expected_memory_ids
expected_top_memory_id
```

The evaluator should not require access to private implementation details of the
SQLite adapter.

It should evaluate through platform-owned retrieval / acceptance interfaces.

## Metrics

The initial experiment should collect only metrics justified by the M7 workload.

Required metrics:

- case pass rate;
- ACCEPT correctness;
- ABSTAIN correctness;
- expected-memory recall@k;
- top-1 correctness when applicable;
- false-positive recall count;
- false-negative recall count;
- evaluation latency;
- deterministic reproducibility across repeated runs.

Optional metrics may be added only if required by the experiment.

## Baseline

The baseline is the currently accepted M7 retrieval architecture:

```text
SQLite
+ FTS5
+ BM25
+ deterministic Retrieval Acceptance Gate
```

No candidate retrieval backend is required for the first phase.

The initial purpose is to prove that the eval mechanism itself can measure the
existing baseline reproducibly.

## Candidate comparison phase

Only after the Eval Runner proves useful should the experiment add a comparison
shape such as:

```text
baseline
   |
   +--> evaluate
   |
candidate
   |
   +--> evaluate
   |
   v
ComparisonResult
```

A candidate must never be promoted simply because it produces a larger numeric
score.

The experiment must define the success metric and guardrails before comparison.

## Success criteria

The M8 experiment is successful only if all of the following are demonstrated:

1. Evaluation cases are represented as reusable data.
2. The same case suite can be executed repeatedly without manual rewriting.
3. The runner produces structured machine-readable results.
4. Relevant retrieval cases produce correct PASS outcomes.
5. Negative cases verify ABSTAIN behavior.
6. Scope-isolation cases are evaluable without special-case infrastructure.
7. Repeated execution of a fixed corpus/query produces reproducible results.
8. Evaluation code remains separate from production retrieval code.
9. No LLM-as-Judge or external eval service is required.
10. The mechanism is reusable enough to plausibly evaluate another platform
    capability without redesigning the core contract.

## Guardrails

The experiment must not:

- modify MemoryStoreContract solely for evaluation;
- modify RetrievalContract solely for evaluation;
- leak raw memory content into default logs or telemetry;
- introduce a persistent eval control plane;
- require an external database;
- require an external eval SaaS;
- require LLM-as-Judge;
- convert evals into CI-blocking guardrails before value is demonstrated;
- make evaluation-provider concepts part of platform domain contracts;
- duplicate normal unit tests without adding evaluation evidence.

## Decision rule

### Accept Evaluation Plane

Accept ADR-0006 only if the experiment demonstrates that the minimal Eval Runner
creates reusable, reproducible evidence and can compare results without coupling
the platform to the evaluated subsystem.

### Defer

Defer if:

- the mechanism works but provides little improvement over tests and Markdown
  evidence;
- the abstraction requires redesign before a second capability can use it;
- evaluation metrics remain too workload-specific to justify a platform plane.

### Reject

Reject the proposed Evaluation Plane if:

- it mainly duplicates the existing test suite;
- it increases complexity without reducing experiment effort;
- it requires a heavy external framework to provide basic value;
- reusable structured evaluation cannot be demonstrated.

## Expected experiment phases

### M8.0 — Baseline and experiment plan

- define current manual evaluation baseline;
- define hypothesis;
- define success criteria and guardrails;
- define first retrieval dataset.

### M8.1 — Evaluation contracts

Introduce only the minimal provider-agnostic domain and contract shapes.

No retrieval-specific implementation belongs in the core contract.

### M8.2 — Deterministic Eval Runner

Implement the smallest runner capable of:

- executing cases;
- invoking an evaluator;
- collecting results;
- summarizing outcomes.

### M8.3 — Retrieval evaluator

Use M7 Memory & Recall as the first real evaluation workload.

### M8.4 — Baseline comparison support

Add comparison only after single-target evaluation is proven useful.

### M8.5 — Evidence and decision

Record results under:

```text
docs/evidence/m8-eval-experiment-results.md
```

Then decide whether ADR-0006 becomes:

```text
Accepted
Deferred
Rejected
```

## Evidence to capture

At minimum:

- exact Git revision;
- evaluation corpus;
- number of cases;
- case outcomes;
- aggregate metrics;
- repeated-run reproducibility;
- evaluation duration;
- implementation complexity;
- failures and unexpected behavior;
- whether a second evaluator can reuse the same core abstractions.

## Initial implementation philosophy

Prefer:

```text
plain Python
+ Pydantic domain models
+ deterministic evaluators
+ existing platform contracts
```

Do not introduce an evaluation framework until the minimal implementation proves
a requirement gap.

## Expected value

If successful, M8 should operationalize the existing architecture process:

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

The goal is not to maximize the number of evals.

The goal is to make architectural evidence reproducible.
