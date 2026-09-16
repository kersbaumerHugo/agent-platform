# M8 Eval-as-Code Experiment Results

- Status: Completed
- Date: 2026-09-16
- Milestone: M8 — Evaluation Plane / Eval-as-Code
- Governing principle: ADR-0002 — Evidence-Gated Architecture
- Related ADR: ADR-0006 — Evaluation Plane / Eval-as-Code
- Evaluated revision: `8e8051e465a9feafaf57f01d644466b989963961`

## Decision

**PROMOTE / ACCEPT**

The M8 experiment demonstrated that a minimal internal Eval-as-Code mechanism
provides reusable, deterministic, machine-readable evaluation evidence across
more than one platform capability without requiring a heavyweight framework,
persistent control plane, external evaluation service, or LLM-as-Judge.

ADR-0006 may be promoted from **Proposed** to **Accepted**.

This decision accepts the minimal Evaluation Plane abstraction that was actually
proven by the experiment. It does not approve deferred capabilities such as
LLM-as-Judge, persistent evaluation storage, automatic architectural promotion,
or external evaluation providers.

## Hypothesis

The experiment tested whether a minimal deterministic evaluation mechanism could:

1. represent evaluation cases as reusable data;
2. execute them through a common runner;
3. produce structured PASS / FAIL / ERROR results;
4. evaluate the accepted M7 retrieval baseline reproducibly;
5. remain independent from specific backends and external eval frameworks;
6. support a second evaluation type without redesigning the evaluation core.

The hypothesis was supported by the experiment.

## Implemented evaluation core

The experiment introduced and validated:

```text
EvaluationCase
EvaluationOutcome
EvaluationResult
EvaluationContract
EvalRunner
```

The core remained provider-agnostic and subsystem-agnostic.

Concrete evaluation semantics were implemented through adapters.

## Evaluation workload 1 — Retrieval

### Target

The accepted M7 Memory & Recall baseline:

```text
SQLiteMemoryStore
    +
SQLiteFTSRetrieval
    +
FTS5 / BM25
    +
LexicalRetrievalAcceptanceGate
    +
RetrievalEvaluator
```

### Dataset

Suite:

```text
m8-retrieval-v0
```

Cases:

```text
4
```

Coverage included:

- relevant query -> ACCEPT;
- expected memory recalled;
- expected top-1 ranking;
- unrelated query -> ABSTAIN;
- cross-scope query -> ABSTAIN.

### Result

```text
pass: 4
fail: 0
error: 0
deterministic_reproducibility: true
duration_seconds: 0.016699902014806867
```

All retrieval cases passed.

The suite was executed twice against independent SQLite databases and produced
the same structured evaluation results.

### Evidence provided

The retrieval suite demonstrated:

- reusable labeled evaluation cases;
- explicit positive and negative behavior;
- ACCEPT correctness;
- ABSTAIN correctness;
- expected-memory recall;
- top-1 correctness;
- scope isolation;
- deterministic repeated execution;
- evaluation through platform-owned retrieval interfaces rather than SQLite
  internals.

## Evaluation workload 2 — Tool capability

### Target

The existing platform tool contract and the real deterministic diagnostic tool:

```text
DiagnosticEchoTool
    |
    v
ToolContract
    |
    v
ToolEvaluator
```

### Dataset

Suite:

```text
m8-tool-v0
```

Cases:

```text
3
```

Coverage included:

- successful tool invocation;
- expected output values;
- run_id preservation;
- tool_name preservation;
- expected validation failure.

### Result

```text
pass: 3
fail: 0
error: 0
deterministic_reproducibility: true
duration_seconds: 0.0020649179932661355
```

All tool capability cases passed.

The suite was executed twice and produced the same structured evaluation
results.

### Architectural significance

The tool evaluator reused the same:

```text
EvaluationCase
EvaluationOutcome
EvaluationResult
EvaluationContract
EvalRunner
```

that had already been used for retrieval evaluation.

No redesign of the evaluation core was required.

This directly satisfies the experiment requirement that a second independent
capability reuse the same abstractions.

## Aggregate experiment result

Across both real evaluation suites:

```text
total cases: 7
pass: 7
fail: 0
error: 0
deterministic suites: 2 / 2
combined measured suite duration: 0.018764820008073002
```

The duration values are evidence that the deterministic V0 is lightweight in
this environment. They are not treated as a formal performance benchmark.

## Machine-readable evidence

Raw structured results were captured as JSON artifacts:

```text
docs/evidence/artifacts/m8-retrieval-v0.json
docs/evidence/artifacts/m8-tool-v0.json
```

This demonstrates that evaluation evidence can be consumed by future comparison,
reporting, or automation without requiring a persistent evaluation database.

## Success-criteria review

### 1. Evaluation cases are reusable data

**PASS**

Both retrieval and tool suites are stored as declarative datasets rather than
being embedded solely in manual procedures.

### 2. The same case suite can be executed repeatedly

**PASS**

Both suites were executed repeatedly without rewriting the cases.

### 3. Results are structured and machine-readable

**PASS**

The runner produces `EvaluationResult` objects and the suite scripts emit JSON
reports.

### 4. Relevant retrieval behavior is evaluated correctly

**PASS**

Positive retrieval cases passed with the expected ACCEPT behavior and expected
memory evidence.

### 5. Negative / abstention behavior is explicit

**PASS**

Unrelated and cross-scope retrieval cases explicitly validated ABSTAIN behavior.

### 6. Scope isolation is evaluable without special infrastructure

**PASS**

The retrieval dataset includes a cross-scope case through the same normal
evaluation path.

### 7. Fixed evaluation is reproducible

**PASS**

Both suites reported:

```text
deterministic_reproducibility: true
```

### 8. Evaluation remains separate from production implementation

**PASS**

Evaluation-specific logic lives behind evaluation adapters and consumes existing
platform contracts. Production retrieval and tool contracts were not redesigned
for the experiment.

### 9. No heavyweight external evaluation infrastructure is required

**PASS**

V0 uses:

```text
plain Python
Pydantic
existing platform contracts
deterministic evaluators
JSON artifacts
```

No LLM-as-Judge, external eval SaaS, dedicated eval database, or persistent eval
service was required.

### 10. The abstraction is reusable beyond one subsystem

**PASS**

Retrieval and tool capability evaluation both reused the same evaluation core
without redesign.

## Guardrail review

The experiment did not:

- replace unit tests;
- replace observability;
- make evaluation a runtime authorization mechanism;
- auto-promote architecture;
- introduce LLM-as-Judge;
- introduce a mandatory external evaluation provider;
- introduce a dedicated evaluation database;
- couple evaluation domain contracts to SQLite, retrieval, MCP, model providers,
  or a specific runtime;
- require sensitive evaluated content to be copied into default telemetry.

## Deviations from the initial plan

The initial experiment plan described baseline-vs-candidate comparison as a
possible later M8 phase.

The experiment intentionally did **not** add a generic comparison abstraction
before a concrete candidate comparison was required.

Instead, the experiment used the second-capability requirement as the stronger
test of whether the evaluation core deserved to become platform architecture.

Baseline-vs-candidate comparison remains a future use of evaluation results and
must itself earn any additional abstraction it requires.

## What was learned

### The abstraction generalized

The same small evaluation core supported both retrieval semantics and tool
capability semantics.

### Workload-specific metrics belong to evaluators

Retrieval needed metrics such as recall and top-1 correctness.

Tool evaluation needed metrics such as invocation success, run_id preservation,
tool-name preservation, and output matching.

No universal quality score was required.

### Deterministic evaluators are sufficient for V0

The first useful Evaluation Plane did not require another LLM to judge outputs.

This keeps the baseline reproducible, explainable, fast, and inexpensive.

### Eval remains distinct from tests

Unit tests continue to verify implementation behavior.

Eval suites represent reusable labeled cases and emit structured evidence about
capability behavior.

The two mechanisms complement each other rather than replacing one another.

## Accepted V0 boundary

M8 accepts the following as the V0 Evaluation Plane:

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
capability-specific deterministic evaluator
      |
      v
EvaluationResult
      |
      +--> PASS / FAIL / ERROR
      +--> metrics
      +--> reason_code
      +--> metadata
```

Supported evidence patterns now include:

- deterministic retrieval evaluation;
- deterministic tool capability evaluation;
- reusable data-driven suites;
- structured JSON result artifacts.

## Explicitly deferred

The following are not accepted as required V0 architecture:

- LLM-as-Judge;
- external evaluation SaaS;
- dedicated evaluation database;
- persistent Evaluation Plane service;
- distributed evaluation workers;
- automatic architecture promotion;
- a universal quality score;
- generic baseline-vs-candidate comparison abstractions;
- agent trajectory scoring;
- human preference collection;
- dashboard UI.

Each remains evidence-gated.

## Final conclusion

The Evaluation Plane earned its place.

The experiment demonstrated reusable and reproducible value with a small
implementation, no external framework, and no redesign when a second independent
capability was introduced.

ADR-0006 should therefore be marked **Accepted**.

The governing principle remains:

> Complexity must earn its place.
