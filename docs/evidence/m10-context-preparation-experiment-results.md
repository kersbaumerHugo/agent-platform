# M10 Context Preparation + Injection V0 — Experiment Results

- Status: Complete
- Decision: Accept ADR-0008
- Date: 2026-09-16
- Evidence baseline revision: `6e65e6741644b18810421d04af2b9d0e5adec4c5`
- Governing principle: ADR-0002 — Evidence-Gated Architecture
- Related ADRs:
  - ADR-0005 — Memory & Recall V0
  - ADR-0006 — Evaluation Plane / Eval-as-Code
  - ADR-0007 — Work API and Deterministic Orchestrator V0
  - ADR-0008 — Context Preparation and Injection V0

## Decision

**Accept.**

M10 demonstrated that explicit `ContextRef[]` selection can be transformed into
a deterministic, source-neutral Context IR and injected through the canonical
provider-neutral model boundary without coupling model adapters to memory,
retrieval, SQLite, BM25, or prompt-construction internals.

The evidence satisfies the ADR-0008 acceptance rule:

```text
explicit context selection
-> deterministic recall plan
-> replaceable context provider
-> source-neutral Context IR
-> deterministic assembly
-> deterministic bounded budgeting
-> byte-stable rendering
-> privilege-safe injection
-> provider-neutral ModelRequest
-> structured operational trace
```

No external RAG framework, vector database, LLM planner, LLM reranker, LLM
summarizer, or dynamic plugin system was required.

## Evidence revision

The implementation/evidence baseline used for this decision is:

```text
6e65e6741644b18810421d04af2b9d0e5adec4c5
```

This revision is the merge of PR #60 and contains the complete M10.1–M10.11
implementation, Eval-as-Code suite, deterministic smoke, generated evidence
artifacts, and the CI-alignment fix discovered during the final smoke PR.

## Implemented V0 boundaries

Canonical domain concepts:

```text
ContextRef
RecallIntent
RecallRequest
RecallPlan
ContextProvenance
ContextItem
ContextContribution
ContextSection
ContextBundle
ContextBudget
BudgetedContextBundle
RenderedContext
ContextProviderResult
ContextPreparationTrace
```

Replaceable behavioral seams:

```text
RecallPlannerContract
ContextProviderContract
ContextAssemblerContract
ContextBudgetPolicyContract
TokenEstimatorContract
ContextRendererContract
ContextInjectorContract
```

Concrete V0 implementations:

```text
DeterministicRecallPlanner
MemoryContextProvider
DeterministicContextAssembler
DeterministicContextBudgetPolicy
Utf8ByteTokenEstimator
MarkdownContextRenderer
ReferenceMessageInjector
ContextTraceBuilder
```

No runtime plugin discovery was introduced. Replaceability is provided through
normal dependency injection.

## Policy versions

The accepted V0 evidence records:

```text
Recall planner
  name: deterministic
  version: v0

Context assembler
  version: v0

Budget policy
  version: canonical-prefix-v0

Token estimator
  version: utf8-bytes-v0

Renderer
  name: markdown
  version: v0

Injector
  name: reference-message
  version: v0

Preparation trace
  version: v0
```

Memory remains the first Context Provider, not the platform definition of
Context.

## Eval-as-Code results

Artifact:

```text
docs/evidence/artifacts/m10-context-preparation-v0.json
```

Result:

```text
case_count: 8
pass: 8
fail: 0
error: 0
deterministic_reproducibility: true
```

The required cases were exercised:

1. LinkedIn + Homelab
2. LinkedIn + Agent Platform
3. Retrieval abstention
4. No selected context
5. Provider-order invariance
6. Budget pressure
7. Injection privilege
8. Provider/model independence

Representative rendered-context hashes:

```text
LinkedIn + Homelab
sha256:aaf2b8872005f8287062b89e7f446909cfcbc86ae13f0b8a369cdfff201477ae

LinkedIn + Agent Platform
sha256:10672dfbdae3c40b883f5c3343e4e1a23f50f4da9e2693acd99443bcea7a9cdf
```

The provider/model-independence case reached the existing `ModelGateway` using a
deterministic fake model while preserving the canonical `ModelRequest` shape.

## End-to-end deterministic smoke

Artifact:

```text
docs/evidence/artifacts/m10-context-preparation-smoke-v0.json
```

Fixed scenario:

```text
Work:
  Write a LinkedIn post about the homelab.

Contexts:
  shared   -> global
  delivery -> app:linkedin
  subject  -> project:homelab

Step:
  draft -> Draft the post.
```

The scenario was executed twice against independent ephemeral SQLite backing
stores.

All deterministic comparison gates were true:

```text
RecallPlan
accepted source IDs
accepted source hashes
ContextBundle
BudgetedContextBundle
rendered bytes
rendered-context hash
injected canonical ModelRequest shape
ContextPreparationTrace
```

Result:

```text
deterministic_reproducibility: true
```

Prepared-context evidence:

```text
rendered-context hash:
sha256:5fde3f2689d62541e2553974d4a58fc0230ac5fbfd8bcc49e85930f0f8e05a52

UTF-8 rendered length:
572 bytes

budget:
384 estimated context-token units available
85 estimated units consumed
0 dropped items
```

Accepted source IDs:

```text
11111111-1111-1111-1111-111111111111
22222222-2222-2222-2222-222222222222
33333333-3333-3333-3333-333333333333
```

Accepted source content hashes:

```text
sha256:6d72fc42de7ef3037f1f5bd69b9722f8a42a4d8f4ea352681fbd8ae3ed5167e4
sha256:3f9abf0375f5f6dc13f9866cb9dbba3ab963693b4f55990bfe03f78c2524d3f4
sha256:6e4343d2afcd5e6a7ece37bd8fdea66b546719084405853a25ebe0daf6609666
```

The smoke artifact stores hashes and identities rather than raw recalled memory
content.

## CI and full-gate evidence

PR #60 exposed a mismatch between the local verification command and CI:
tests imported the smoke runner successfully under `python -m pytest`, while CI
used the `pytest` console entrypoint and could not resolve `scripts`.

The CI contract was aligned with the local full gate before acceptance:

```text
python -m compileall -q src tests scripts
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m mypy src
python -m pytest
python -m build
```

Successful GitHub Actions run:

```text
CI run: 124
head revision: 61ae57a016433d9976da1bb25b3de585151026ec
Python: 3.12.14

Syntax:    PASS
Lint:      PASS
Typecheck: PASS
Tests:     PASS
Package:   PASS

pytest:
307 passed
1 non-blocking Starlette/anyio deprecation warning
```

The local full static/type/test/build gate was also run before publication of the
M10.11 smoke PR.

## Acceptance criteria assessment

ADR-0008 success criteria are satisfied:

```text
[PASS] source-neutral canonical Context IR
[PASS] Memory is one Context Provider, not Context itself
[PASS] explicit M9 ContextRef allow-list remains authoritative
[PASS] deterministic recall planning
[PASS] no implicit namespace selection
[PASS] provider-specific retrieval details stop at provider boundary
[PASS] deterministic source-neutral assembly
[PASS] bounded deterministic budgeting
[PASS] byte-stable deterministic rendering
[PASS] injection occurs at canonical ModelRequest boundary
[PASS] retrieved content is not promoted to system privilege
[PASS] structured trace uses IDs/hashes/versions by default
[PASS] fixed source state reproduces Context IR and rendered hash
[PASS] no LLM required for preparation policies
[PASS] no external RAG/context framework required
[PASS] M8 Eval-as-Code emits machine-readable acceptance evidence
```

## Complexity assessment

The additional complexity earned its place because each accepted seam corresponds
to independently variable behavior:

```text
planning   -> query construction policy may change
provider   -> source backend may change
assembly   -> composition policy may change
budgeting  -> retention policy may change
estimator  -> model/token family may change
rendering  -> representation may change
injection  -> execution placement may change
```

The experiment did not add abstractions for concepts that lacked independent
semantic value. In particular, no `ExecutionContext`, dynamic plugin loader,
Context Resolver, or separate standing-memory service was promoted into V0.

## Deferred capabilities

The following remain explicitly deferred and must independently earn their place:

```text
automatic Context Resolver
standing + task-relevant multi-lane recall infrastructure
LLM recall planner
LLM query expansion
embedding retrieval
hybrid retrieval
reranker
GraphRAG
semantic deduplication
semantic conflict resolution
LLM context compression
LLM summarization
dynamic plugin discovery
provider-specific tokenizers
persistent context snapshots
historical replay guarantees
cross-scope global ranking
context cache
automatic source conflict resolution
```

The deterministic V0 query strategy remains:

```text
objective + step input
```

Standing versus task-relevant recall remains a hypothesis rather than accepted
architecture because the V0 acceptance suite did not require a second recall
lane.

## Consequences

Positive:

- Context is now independent from Memory and retrieval implementation details.
- Model-provider adapters remain context-agnostic.
- Context preparation is deterministic and reproducible for fixed source state.
- Context size is bounded before injection.
- Retrieved text cannot become a new system message by structure.
- Operational evidence is separable from model-facing content.
- Additional context sources can be tested behind the existing provider boundary.
- Future policy changes can be evaluated against the accepted V0 baseline.

Trade-offs:

- `utf8-bytes-v0` is an approximation rather than an exact provider tokenizer.
- `canonical-prefix-v0` intentionally prefers precedence over packing efficiency.
- V0 does not provide historical reconstruction after source mutation.
- The deterministic query baseline may miss standing preferences in workloads
  whose task text does not lexically overlap with those preferences.
- Memory is the only demonstrated provider at acceptance time.

These limitations are explicit and do not invalidate the V0 acceptance criteria.

## Final decision

ADR-0008 is **Accepted**.

M10 — Context Preparation + Injection V0 is complete.

The next capabilities should build on this accepted baseline rather than expanding
M10 with speculative functionality.

The governing rule remains:

> Complexity must earn its place.
