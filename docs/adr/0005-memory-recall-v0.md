# ADR-0005: Memory and Recall V0 with lexical-first retrieval

- Status: Accepted
- Date: 2026-09-15

## Trigger

The Agent Platform can execute agentic workloads through replaceable runtime and model-provider contracts, including a validated local inference backend.

The next functional gap was persistent memory across executions.

Before M7, agents had no platform-owned mechanism to:

- explicitly persist durable information;
- recover relevant information in a later execution;
- reject irrelevant or insufficient retrieved context;
- isolate memories between scopes.

This ADR defines the minimum architecture required to close that gap.

## Principle

Memory, retrieval and context injection are separate concerns.

```text
Memory != Retrieval != Context Injection
```

Memory owns persistence.

Retrieval owns search and ranking.

The Retrieval Acceptance Gate decides whether retrieved evidence is sufficient to use.

Context injection is a later integration concern and is not coupled to the persistence backend.

## Decision

M7 V0 uses platform-owned contracts for memory and retrieval.

The accepted baseline backend is SQLite with FTS5 and BM25.

No embeddings, vector database, semantic reranker or LLM-based retrieval decision is required for V0.

The architecture is:

```text
Agent / Runtime
      |
      | capability call
      v
MCP Adapter
      |
      v
ToolRegistry
      |
      +----------------------+
      |                      |
      v                      v
memory_remember         memory_recall
      |                      |
      v                      v
MemoryStoreContract    RetrievalContract
      |                      |
      v                      v
SQLite                 SQLite FTS5 / BM25
                             |
                             v
                  Retrieval Acceptance Gate
                             |
                       ACCEPT / ABSTAIN
```

## Contracts

The platform owns the memory and retrieval contracts.

Implemented domain concepts include:

```text
MemoryRecord
MemoryScope
MemoryStoreContract
RetrievalQuery
RetrievalHit
RetrievalContract
RetrievalAcceptanceDecision
```

Backend-specific concepts do not leak into the contracts.

## Memory write path

Memory creation is explicit in V0.

The platform exposes:

```text
memory_remember
```

The runtime or agent may invoke this capability when durable information should be stored.

V0 does not automatically extract memories from every conversation or model response.

Automatic memory extraction requires separate evidence and policy.

## Recall path

The platform exposes:

```text
memory_recall
```

Recall performs:

```text
query
  -> lexical retrieval
  -> ranking
  -> acceptance evaluation
  -> results or abstention
```

Retrieval is allowed to return no usable context.

Top-k retrieval is not equivalent to sufficient evidence.

## Retrieval Acceptance Gate

The acceptance gate belongs to the Retrieval Plane.

It remains independent from the storage backend.

The accepted V0 gate uses deterministic lexical signals, including:

- presence or absence of hits;
- query-term coverage;
- scope constraints;
- top-hit score metadata.

The decision produces:

```text
decision
reason_code
metadata
```

Initial decisions are:

```text
ACCEPT
ABSTAIN
```

Retry and fallback strategies remain deferred.

## Scope isolation

Every persistent memory belongs to an explicit scope or namespace.

Retrieval does not search outside the requested scope.

Scope isolation is a correctness and security requirement, not a ranking hint.

## Persistence

The SQLite database is runtime state and does not live inside immutable release directories.

The accepted deployment location is:

```text
/var/lib/agent-platform/memory/memory.sqlite3
```

Application releases remain replaceable without deleting durable memory.

## Observability

Memory and retrieval operations are exposed through the existing tool lifecycle observability boundary.

Raw memory content is not emitted into default acceptance telemetry.

`run_id` remains the execution correlation identifier.

Further dedicated retrieval metrics may be added when they earn their place through an operational or evaluation requirement.

## Integration strategy

M7 V0 reuses the existing platform capability boundary.

The write/read flow is:

```text
Agent
 -> MCP
 -> ToolRegistry
 -> memory_remember / memory_recall
 -> platform-owned memory/retrieval contracts
```

This avoids modifying `ModelContract` or `RuntimeContract` solely to add persistence.

Automatic context injection remains deferred.

## Validation evidence

The complete validation is recorded in:

```text
docs/evidence/m7-memory-recall-results.md
```

Observed evidence includes:

- explicit memory write through MCP and ToolRegistry;
- recall from a later execution with a different `run_id`;
- successful recall after MCP SIGKILL and systemd recovery;
- explicit ABSTAIN for unrelated queries;
- no cross-scope retrieval;
- successful recall after complete `agent01` reboot;
- successful recall after application roll-forward from `7f8f1a9` to `f746f16`;
- persistent SQLite state outside immutable release directories.

## V0 success criteria

M7 V0 is accepted because the platform proved all of the following:

1. A memory written during one execution persists.
2. A later execution can recall that memory.
3. Memory survives process restart and application release changes.
4. Retrieval ranking is deterministic for a fixed corpus and query.
5. Unrelated queries can produce ABSTAIN.
6. Scope isolation prevents cross-scope retrieval.
7. Memory content is not exposed through default acceptance telemetry.
8. The capability works through the existing platform-owned tool boundary.

## Deployment finding

During validation, the SQLite database was initially observed with mode `0644`.

It was corrected to `0640`.

A minimal deployment hardening follow-up should make restrictive creation permissions automatic, for example through:

```text
UMask=0027
```

on the MCP service or equivalent explicit persistent-state provisioning.

This finding does not invalidate the architecture decision.

## Deferred complexity

The following remain outside V0:

```text
embeddings
vector databases
dense retrieval
hybrid retrieval
LLM reranking
automatic memory extraction
automatic context injection
memory consolidation
memory summarization
memory decay
knowledge graphs
```

These capabilities require evidence that the lexical baseline is insufficient.

## Evolution path

The evidence-gated progression remains:

```text
V0
SQLite + FTS5/BM25
        |
        | measure retrieval quality
        v
V1 candidate
Dense retrieval
        |
        | measurable gain required
        v
V2 candidate
Hybrid lexical + dense
        |
        | measurable gain required
        v
V3 candidate
Reranking
```

Skipping directly to a more complex stage is not the default.

## Evaluation signals

The lexical baseline should be measured before any semantic retrieval candidate is promoted.

Useful signals include:

- recall@k on a labeled memory corpus;
- precision@k;
- accepted-vs-abstained correctness;
- task success rate with recall enabled;
- false-positive recall rate;
- retrieval latency;
- storage size;
- deterministic reproducibility.

A semantic candidate must demonstrate measurable benefit against this baseline.

## Re-evaluation triggers

This decision should be revisited when evidence shows that:

- lexical recall misses relevant memories at an unacceptable rate;
- corpus size makes the SQLite baseline inadequate;
- semantic similarity materially improves task success;
- multi-process concurrency exceeds the SQLite operational envelope;
- automatic recall demonstrably outperforms explicit capability invocation.

Until one of those conditions exists, SQLite FTS5/BM25 remains the minimum sufficient baseline.
