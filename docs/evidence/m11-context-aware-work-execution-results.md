# M11 Context-Aware Work Execution V0 — Experiment Results

- Status: Completed
- Date: 2026-09-17
- Decision: Accepted
- Related ADR: ADR-0009 — Context-Aware Work Execution V0
- Governing principle: ADR-0002 — Evidence-Gated Architecture
- Real-smoke platform revision: `aff85e89e6da08e73184a42702c3de3f93ec24cf`

## Executive result

M11 demonstrated that explicit Work context can participate in actual agent execution through the accepted M10 preparation and injection boundaries without making Runtime or model-provider adapters aware of Memory, Retrieval, BM25, or Context IR.

The promoted V0 strategy is:

```text
WorkRequest
-> WorkOrchestrator
-> step-aware Context Preparation
-> ContextPreparationResult
-> RunAgent allocates run_id
-> bind(run_id -> prepared context)
-> RuntimeContract
-> DSHRuntime
-> internal OpenAI-compatible Model Gateway
-> resolve(run_id)
-> ReferenceMessageInjector
-> canonical ModelRequest
-> ModelGateway
-> ModelContract
-> response
-> release(run_id)
```

No first-class `ExecutionContext`, queue, workflow framework, distributed state store, scheduler, or persistent run-context registry was required.

## Decision

**Accepted — Strategy B: run-scoped ModelRequest injection.**

The experiment supports the hypothesis that the existing `run_id` is sufficient for the V0 handoff between Work context preparation and live model execution.

`ExecutionContext` did not earn its place in M11.

The process-local binding registry is accepted for the current single-process topology. A persistent/distributed binding backend remains deferred until a deployment boundary requires it.

## Eval-as-Code evidence

Artifact:

```text
docs/evidence/artifacts/m11-context-aware-execution-v0.json
```

Result:

```text
9 PASS
0 FAIL
0 ERROR
deterministic_reproducibility = true
```

The suite demonstrates binding cleanup, run isolation, fail-closed behavior, system-message preservation, provider neutrality, and Work/Run/context correlation.

## Deterministic integration smoke

Artifact:

```text
docs/evidence/artifacts/m11-context-aware-execution-smoke-v0.json
```

Result:

```text
deterministic_reproducibility = true
invariants_passed = true
all_bindings_cleared = true
raw_context_absent = true
```

The smoke exercised SQLite FTS5 retrieval, MemoryContextProvider, preparation, run-scoped binding, internal gateway injection, ModelGateway, and a deterministic model.

## Supervised real DSH smoke

### OpenRouter backend

Artifact:

```text
docs/evidence/artifacts/m11-real-dsh-work-smoke-openrouter.json
```

Result: **PASS**

The path completed through real `POST /work`, DSHRuntime, the internal Model Gateway, OpenRouter, and a successful WorkResult.

### Local GPU backend

Artifact:

```text
docs/evidence/artifacts/m11-real-dsh-work-smoke-local.json
```

Result: **PASS**

Observed evidence:

```text
work_succeeded = true
run_succeeded = true
selected_namespace_accepted = true
prepared_context_hash_present = true
expected_marker_returned = true
dsh_runtime_metric_seen = true
model_gateway_success_metric_seen = true
```

The local real path was:

```text
POST /work
-> SQLite FTS5
-> Retrieval Acceptance
-> MemoryContextProvider
-> PrepareContext
-> run-scoped binding
-> DSHRuntime
-> internal Model Gateway
-> LocalOpenAIModelAdapter
-> llama-server
-> local NVIDIA GPU
-> successful WorkResult
```

The local smoke used DSH profile `sdk-minimal`.

This provides supervised real evidence that the M11 execution architecture is model-provider independent: the same platform boundary completed successfully with both a remote OpenRouter backend and a local OpenAI-compatible backend.

## Local DSH profile finding

A supervised attempt using the full DSH `sdk` profile with the local model did not complete within the current provider timeout.

Observed behavior:

```text
Model Gateway request
-> LocalOpenAIModelAdapter
-> ReadTimeout at approximately 90 seconds
-> DSH retry / additional model turn
-> repeated timeout
-> Run failure
```

Control tests showed:

```text
dev01 -> local /v1/models                  PASS, ~milliseconds
direct local chat completion               PASS, ~8 seconds
Agent Platform -> local Model Gateway      PASS, ~2.7 seconds
DSH sdk-minimal -> local Model Gateway     PASS
DSH sdk -> local Model Gateway             timeout under current limits
```

This is recorded as a profile/workload performance limitation, not an M11 architectural failure. M11 does not claim that every DSH profile is performant on every model/backend.

No timeout increase or new architecture was promoted merely to make the heavier profile pass.

## Full quality gate

The full repository gate passed after the live-smoke additions:

```bash
python -m compileall -q src tests scripts
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m mypy src
python -m pytest -q
python -m build
git diff --check
```

Result: **PASS**

## Success criteria assessment

All M11 acceptance criteria are satisfied:

1. actual WorkStep execution uses M10 preparation — PASS;
2. explicit ContextRef allow-list remains authoritative — PASS;
3. preparation is step-aware — PASS;
4. RuntimeRequest remains free from retrieval implementation details — PASS;
5. provider adapters remain context-agnostic — PASS;
6. context is injected at canonical ModelRequest — PASS;
7. system privilege is preserved — PASS;
8. no-context Runs/Work remain backward-compatible — PASS;
9. concurrent Runs are isolated — PASS;
10. binding lifecycle is cleaned on success and failure — PASS;
11. missing required context state fails closed — PASS;
12. Work/step/run/context evidence is correlatable — PASS;
13. deterministic Eval-as-Code evidence passes — PASS;
14. deterministic integration smoke passes — PASS;
15. supervised real DSH `/work` smoke passes — PASS;
16. no queue/framework/distributed state store is required — PASS.

## Complexity assessment

Complexity that earned its place:

```text
ContextPreparationResult
InMemoryRunContextBindings
configuration-driven runtime composition
WorkStepResult.context_trace
```

Complexity that did not earn its place:

```text
ExecutionContext
Redis
persistent/distributed binding registry
workflow framework
queue
scheduler
new WorkExecutionTrace abstraction
provider-specific context integration
```

Candidate A, prompt composition before Runtime, was not promoted because it would weaken the accepted M10 injection boundary.

Candidate C, first-class `ExecutionContext`, was not required.

## Accepted constraints

The V0 run-context registry is process-local.

Therefore the accepted topology assumes that the Work execution path and the internal Model Gateway resolve bindings from the same application process.

If future deployment separates these components across processes or hosts, that topology change becomes the trigger for a new evidence-gated decision about persistent/distributed binding.

## Deferred capabilities

M11 does not introduce:

```text
automatic Context Resolver
parallel Work execution
DAG orchestration
persistent Work queue
scheduler
workflow engine
Redis
distributed run-context binding
automatic retry policy
cross-step artifact propagation
sandbox redesign
tool authorization policy engine
semantic retrieval
embedding retrieval
reranking
LLM query planning
LLM context compression
```

## Final conclusion

M11 closes the gap between accepted context preparation and actual Work execution.

The evidence supports Strategy B because it preserves the M9/M10 boundaries, reuses the existing `run_id`, keeps Runtime and model-provider adapters context-source agnostic, preserves privilege separation, works with real DSH execution, and requires only process-local state justified by the current topology.

**ADR-0009 is Accepted.**

> Complexity must earn its place.
