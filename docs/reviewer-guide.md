# Agent Platform — technical reviewer guide

> Snapshot: 2026-10-26; audited against `main` at
> `2cefa5c5292459df9020eab2c6bd2324924fbd64` (2026-10-07).
> This document describes an experimental homelab project, not a generally
> available managed service. **Implementation, test coverage and live evidence
> are different claims.**

For the complete current implementation inventory, see
[architecture as built](architecture-as-built.md),
[capability status](capability-status.md), and
[post-M15 engineering changes](evidence/post-m15-engineering-changes.md).
The referenced 2026-10-07 commit is the latest **application-code** snapshot
reviewed; the 2026-10-26 merge `7279667b` updated documentation only.

## Why this exists (two minutes)

I am exploring which responsibilities should belong to an agent *platform*,
rather than to individual model-driven agents. The central hypothesis is that
model providers, runtimes and capability implementations should be replaceable
behind explicit contracts, with evaluation and authority boundaries owned by
the platform. The practical use case is a **supervised developer agent** that
inspects a repository, proposes changes, verifies them and opens a PR—but
does not approve its own merge.

The governing rule is **Complexity Must Earn Its Place**. The project may have
violated that rule in places; critical assessment is welcome.

## What the repository actually demonstrates

| Capability | What is established | Start with |
| --- | --- | --- |
| Model/runtime adapters | OpenRouter and local OpenAI-compatible model adapters, an internal OpenAI-compatible gateway, DSH and a separate tool-calling runtime | `src/agent_platform/api/composition.py`, `docs/evidence/m14-usable-agent-runtime-results.md` |
| Agentic tool execution | A repository-aware `POST /runs` flow that uses a typed repository-inspection capability through RepoWise | `docs/evidence/m14-usable-agent-runtime-results.md` |
| Memory & retrieval | SQLite memory plus lexical SQLite FTS5/BM25 and deterministic ACCEPT/ABSTAIN | `docs/evidence/m7-memory-recall-results.md`, ADR-0005 |
| Work context | Explicit-context, sequential `POST /work`; M11 binds prepared context to a run and injects it through the Model Gateway | `docs/evidence/m11-context-aware-work-execution-results.md`, ADR-0009 |
| Evaluation & observability | Deterministic Eval-as-Code results and separate logging/metrics/tracing instrumentation | `docs/evidence/m8-eval-experiment-results.md`, `docs/architecture.md` |
| Supervised coding | Recorded live inspect → code → verify → PR → CI → human merge, including a later two-tool-round run | `docs/evidence/m15-trusted-developer-agent-results.md` |
| Later coding gates | Bounded verification repair and semantic review of a verified ChangeSet before publication exist in source and dedicated tests | `src/agent_platform/application/supervised_coding_publication.py`, `tests/unit/test_supervised_coding_repair.py`, `tests/unit/test_worker_coding_semantic_review.py` |

The recorded end-to-end M15 run does **not**, by itself, validate the later
semantic-review gate live. Similarly, code and unit tests are not a claim of
independent security assessment.

## Architecture in one glance

```text
POST /runs or /work
  -> RunAgent / WorkOrchestrator
  -> configured RuntimeContract (fake, dsh, tool-calling)
  -> ModelGateway -> OpenRouter or local OpenAI-compatible provider
  -> typed ToolRegistry + static authorization
       -> repository.inspect (RepoWise)
       -> optional supervised coding.execute
            -> trusted sandbox -> proposed ChangeSet
            -> authoritative verifier
            -> bounded repair on verification rejection (up to two)
            -> semantic review gate
            -> trusted publisher -> GitHub PR -> human merge
```

This is a high-level composite of several configurations; **not every arrow
runs in every deployment**. Coding requires explicit configuration and trusted
services. Context preparation applies to Work runs with configured context
support. The MCP server is a separate protocol adapter, not a claim that every
tool call must use MCP.

## A good path through the repository

1. Read the main [README](../README.md), [architecture as built](architecture-as-built.md) and [capability matrix](capability-status.md).
2. Verify the accepted [M11](evidence/m11-context-aware-work-execution-results.md),
   [M14](evidence/m14-usable-agent-runtime-results.md) and
   [M15](evidence/m15-trusted-developer-agent-results.md) evidence.
3. Read [ADR-0002](adr/0002-evidence-gated-architecture.md) and
   [ADR-0004](adr/0004-trusted-self-development-boundary.md) for design intent.
4. Read the [post-M15 change inventory](evidence/post-m15-engineering-changes.md), then inspect `src/agent_platform/api/composition.py`,
   `src/agent_platform/adapters/runtimes/tool_calling.py`, and
   `src/agent_platform/application/supervised_coding_publication.py` for
   current behavior.

For a local dependency-light baseline:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

These local commands test repository code; they do not exercise live external
models, Docker sandbox services, the homelab or GitHub PR publication.
For provider and trusted-stack setup, start from `README.md` and
`deploy/trusted/README.md`; never reuse example credentials or LAN endpoints.

## Risks, limitations and review questions

- **Scope:** Is the platform/runtime distinction buying real reuse, or are the
  abstractions outrunning the smallest useful vertical slice?
- **Latency:** The historical M15.6 live coding workflow recorded approximately
  529 seconds. What should be simplified or measured before optimizing it?
- **Security:** Are the trust boundaries credible, and where are potential
  bypasses or mismatches between verified ChangeSet and published ChangeSet?
  What threats remain outside the current validation?
- **Review quality:** Can a semantic review by a model add reliable value over
  authoritative tests without becoming a second speculative agent layer?
- **Operability:** Run-context bindings are process-local; the MCP interface
  is designed for trusted networks. When (if ever) is a distributed control
  plane justified?
- **Provider compatibility:** Provider choice is configuration-driven; there
  is no established automatic fallback, SLA or multi-tenant enforcement.
- **Default behavior:** `AGENT_PLATFORM_RUNTIME=fake` unless explicitly
  overridden; launching FastAPI alone is not a proof of real agent execution.

The most useful feedback is not a feature wishlist. Please point out
**unnecessary abstractions, false assumptions, weak evidence, missing
boundaries and the smallest changes that would improve a real end-to-end
workflow**.

## Evidence policy

- `docs/adr/`: recorded design choices, not runtime proof.
- `docs/evidence/`: historical experiment reports and artifacts.
- `src/` + `tests/`: current implementation and executable test cases.
- Live homelab conditions can drift from the Git snapshot.
- A passed test suite or CI is narrower than a production reliability claim.
