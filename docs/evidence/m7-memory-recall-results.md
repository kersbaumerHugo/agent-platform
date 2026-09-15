# M7 Memory & Recall V0 — Validation Results

- Status: Completed
- Date: 2026-09-15
- Decision: Accepted
- Governing ADR: ADR-0005

## Objective

Validate the minimum platform-owned Memory & Recall architecture using:

- explicit durable memory writes;
- SQLite persistence;
- SQLite FTS5/BM25 lexical retrieval;
- deterministic Retrieval Acceptance Gate;
- ACCEPT / ABSTAIN semantics;
- explicit scope isolation;
- MCP / ToolRegistry capability integration;
- persistence across executions, process recovery, guest reboot and application releases.

## Validated architecture

```text
Agent / MCP Client
        |
        v
MCP Adapter
        |
        v
ToolRegistry
        |
        +-----------------------+
        |                       |
        v                       v
memory_remember            memory_recall
        |                       |
        v                       v
MemoryStoreContract       RetrievalContract
        |                       |
        v                       v
SQLite                  SQLite FTS5 / BM25
                                |
                                v
                    Retrieval Acceptance Gate
                                |
                         ACCEPT / ABSTAIN
```

Memory, Retrieval and Context Injection remain separate concerns.

```text
Memory != Retrieval != Context Injection
```

## Environment

Deployment target:

```text
agent01
192.168.10.30
Debian 13
systemd
```

Persistent memory:

```text
/var/lib/agent-platform/memory/memory.sqlite3
```

Runtime identity:

```text
agent-platform:agent-platform
```

Final observed database permissions:

```text
0640
```

## Persistence experiment

A memory was written through the real MCP capability boundary.

Memory:

```text
id: 47fa4ca4-e5b7-47f9-9e16-95fca5bcac41
namespace: m7-e2e
content: M7 persistence survives restart.
```

The write succeeded through:

```text
MCP
 -> ToolRegistry
 -> memory_remember
 -> MemoryStoreContract
 -> SQLite
```

## Cross-run recall

A later execution used a different `run_id` and successfully recalled the memory.

Observed decision:

```text
decision: accept
reason_code: lexical_evidence
query_term_coverage: 1.0
```

Result: **PASS**

## Process-failure recovery

The MCP process was terminated with SIGKILL.

systemd automatically restored the service with a new process.

After recovery, a later execution recalled the previously stored memory successfully.

Result: **PASS**

## Abstention

An unrelated query was executed in the correct namespace.

Query:

```text
kubernetes cluster autoscaling
```

Observed result:

```text
decision: abstain
reason_code: no_hits
memories: []
```

Result: **PASS**

## Scope isolation

The known memory was queried using another namespace.

Observed result:

```text
decision: abstain
reason_code: no_hits
memories: []
```

No cross-scope memory was exposed.

Result: **PASS**

## Guest reboot persistence

The complete `agent01` guest was rebooted.

After boot:

```text
agent-platform-api.service: active
agent-platform-mcp.service: active
API health: OK
memory.sqlite3: present
```

The same previously stored memory was successfully recalled after boot.

Result: **PASS**

## Application release persistence

The memory was originally created while the active application release was:

```text
7f8f1a9976bc788bbf3ffa747e5b3227f87b35da
```

A new application revision was then deployed:

```text
f746f1616d980b285bec8edb36dbf4b6be64b9a4
```

The persistent database remained outside both immutable releases.

After the roll-forward, the original memory was recalled through the new release.

Observed result:

```text
decision: accept
reason_code: lexical_evidence
query_term_coverage: 1.0
```

Result: **PASS**

## Success criteria

| Criterion | Result |
|---|---|
| Memory persists across executions | PASS |
| Later execution can recall memory | PASS |
| Process restart/recovery persistence | PASS |
| Guest reboot persistence | PASS |
| Application release persistence | PASS |
| Deterministic lexical ranking baseline | PASS |
| Unrelated query can ABSTAIN | PASS |
| Scope isolation | PASS |
| Capability works through MCP / ToolRegistry | PASS |
| Raw memory excluded from default acceptance telemetry | PASS |

## Finding — SQLite file permissions

During deployment validation, the SQLite database was observed with mode:

```text
0644
```

It was corrected to:

```text
0640
```

This did not affect functional validation, but automatic enforcement should be added as deployment hardening.

Candidate minimal fix:

```text
UMask=0027
```

on the MCP systemd service, or equivalent explicit persistent-state provisioning.

This finding does not justify introducing a new persistence backend.

## Decision

Accept the M7 Memory & Recall V0 architecture.

SQLite + FTS5/BM25 demonstrated sufficient capability for the current requirements without requiring:

- embeddings;
- vector databases;
- dense retrieval;
- hybrid retrieval;
- reranking;
- automatic memory extraction;
- automatic context injection.

Future retrieval complexity remains evidence-gated.

Complexity must earn its place.
