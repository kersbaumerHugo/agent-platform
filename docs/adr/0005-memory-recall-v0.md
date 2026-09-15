# ADR-0005: Memory and Recall V0 with lexical-first retrieval

- Status: Proposed
- Date: 2026-09-15

## Trigger

The Agent Platform can execute agentic workloads through replaceable runtime and model-provider contracts, including a validated local inference backend.

The next functional gap is persistent memory across executions.

Agents currently have no platform-owned mechanism to:

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

Context injection is a later integration concern and must not be coupled to the persistence backend.

## Decision

M7 V0 will implement platform-owned contracts for memory and retrieval.

The baseline backend will use SQLite with FTS5 and BM25.

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

M7 should begin with platform-owned contracts rather than a storage-specific API.

Initial domain concepts should include equivalents of:

```text
MemoryRecord
MemoryScope
MemoryStoreContract
RetrievalQuery
RetrievalHit
RetrievalContract
RetrievalAcceptanceDecision
```

Backend-specific concepts must not leak into the contracts.

## Memory write path

Memory creation is explicit in V0.

The platform will expose a capability equivalent to:

```text
memory_remember
```

The runtime or agent may invoke this capability when durable information should be stored.

V0 will not automatically extract memories from every conversation or model response.

Automatic memory extraction requires separate evidence and policy.

## Recall path

The platform will expose a capability equivalent to:

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

Retrieval must be able to return no usable context.

Top-k retrieval is not equivalent to sufficient evidence.

## Retrieval Acceptance Gate

The acceptance gate belongs to the Retrieval Plane.

It must remain independent from the storage backend.

V0 may use deterministic signals such as:

- number of matching results;
- lexical score;
- query-term coverage;
- relative score distribution;
- scope constraints;
- source metadata.

The decision must produce at least:

```text
decision
reason_code
metadata
```

Initial decisions:

```text
ACCEPT
ABSTAIN
```

Retry and fallback strategies may be added later if justified.

## Scope isolation

Every persistent memory must belong to an explicit scope or namespace.

Retrieval must never search outside the requested scope unless an explicit cross-scope policy exists.

Scope isolation is a correctness and security requirement, not a ranking hint.

## Persistence

The SQLite database is runtime state and must not live inside immutable release directories.

The expected deployment location is conceptually:

```text
/var/lib/agent-platform/memory/
```

The exact filesystem layout remains a deployment concern.

Application releases must remain replaceable without deleting durable memory.

## Observability

Memory and retrieval operations must expose structured telemetry.

V0 should measure:

- memory writes;
- recall requests;
- recall latency;
- hit count;
- accepted recalls;
- abstentions;
- retrieval errors.

Raw memory content must not be emitted into logs, metrics or traces by default.

`run_id` should remain the execution correlation identifier.

## Initial integration strategy

M7 V0 should reuse the existing platform capability boundary.

The first write/read flow should be:

```text
Agent
 -> MCP
 -> ToolRegistry
 -> memory_remember / memory_recall
 -> platform-owned memory/retrieval contracts
```

This avoids modifying ModelContract or RuntimeContract solely to add persistence.

Automatic context injection remains deferred.

## V0 success criteria

M7 V0 is complete when the platform can prove all of the following:

1. A memory written during one execution persists.
2. A later execution can recall that memory.
3. Memory survives process restart and application release changes.
4. Retrieval ranking is deterministic for a fixed corpus and query.
5. Unrelated queries can produce ABSTAIN.
6. Scope isolation prevents cross-scope retrieval.
7. Memory content is not exposed through default telemetry.
8. The capability works through the existing platform-owned tool boundary.

## Deferred complexity

The following are explicitly outside V0:

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

The intended evidence-gated progression is:

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

- recall@k on a small labeled memory corpus;
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
