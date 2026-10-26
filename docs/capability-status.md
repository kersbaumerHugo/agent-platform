# Capability status — implementation versus evidence

> Audited 2026-10-26 against `main` at `7279667b9790205002c22a663e07aa2cb0ff0d1d`.
> The last application-code merge before this documentation review was
> `2cefa5c5292459df9020eab2c6bd2324924fbd64` (2026-10-07).
> This is a source-and-recorded-evidence inventory, **not a live environment audit**.

## How to read this matrix

- **Implemented**: the code/contract is present in `src/` or deployment configuration.
- **Automated tests**: a relevant test suite exists. This does not assert that the
  suite passed on every possible model, image or host. The 2026-10-26 GitHub CI
  for the documentation merge passed, but does not perform a full live smoke.
- **Recorded live evidence**: a repository document records execution through a
  real runtime/provider/deployment. It is historical and may predate newer code.
- **Spike**: exploratory code, without a claim of accepted production composition.
- **Deferred**: not demonstrated as an operational platform capability.

These dimensions are deliberately separate: *implemented* and *automated-test
coverage* never imply *live-validated*, much less *production-ready*.

| Capability | Implementation / tests | Recorded evidence or status | Key references |
| --- | --- | --- | --- |
| Runtime abstraction and adapters | Implemented; fake, DSH and tool-calling compositions | M14 documents a real tool-calling run | `src/agent_platform/api/composition.py`; `docs/evidence/m14-usable-agent-runtime-results.md` |
| Model Gateway | Implemented; OpenRouter and local OpenAI-compatible adapters | M11 real `/work` smokes on both backends; M14 local tool call | `src/agent_platform/application/model_gateway.py`; M11/M14 reports |
| OpenAI-compatible ingress | Implemented at `/internal/v1` | Internal gateway path exercised by M11/M14; no blanket compatibility claim | `src/agent_platform/api/openai_compat.py` |
| Typed capabilities, registry, static authorization | Implemented and tested | Repository-inspection path exercised in M14 | `src/agent_platform/application/tool_registry.py`; `src/agent_platform/application/capability_authorization.py` |
| MCP tool transport | Implemented and tested | Early tool-loop evidence, trusted/local-network assumption | `src/agent_platform/api/mcp.py`; `tests/unit/test_mcp_transport_security.py` |
| SQLite memory and lexical retrieval | Implemented and tested | M7 persistence and scope-isolation experiments | `src/agent_platform/adapters/memory/sqlite.py`; `docs/evidence/m7-memory-recall-results.md` |
| Retrieval ACCEPT/ABSTAIN | Implemented and tested | M7/M8 deterministic baseline, not semantic relevance proof | `src/agent_platform/application/retrieval_acceptance.py`; `docs/evidence/m8-eval-experiment-results.md` |
| Work orchestration | Implemented, sequential/fail-fast | M9 experiment; M11 real context-aware integration | `src/agent_platform/application/work_orchestrator.py`; M9/M11 evidence |
| Context preparation/injection | Implemented and tested | M10 isolated; M11 live `/work` with selected context | `docs/evidence/m11-context-aware-work-execution-results.md` |
| Eval-as-Code | Implemented and tested | M8 deterministic acceptance artifacts | `src/agent_platform/application/eval_runner.py`; `docs/evidence/m8-eval-experiment-results.md` |
| Logs, Prometheus, OpenTelemetry | Implemented | Recorded integration; do not assume traces across all processes | `src/agent_platform/adapters/observability/`; `docs/architecture.md` |
| Repository-aware agent | Implemented with RepoWise provider | M14 live local-model `/runs` smoke | `src/agent_platform/adapters/repository/`; M14 evidence |
| Supervised coding to PR | Implemented and tested | M15 live PR #84, later M15.6 PR #89; human merge | `docs/evidence/m15-trusted-developer-agent-results.md` |
| Trusted sandbox/verifier/publication | Implemented and tested | M12 boundary experiments plus M15 operational smoke | `src/agent_platform/trust/`; `docs/evidence/m12-6-verified-publication-integrity-results.md` |
| Worker workspace hygiene, planning, phase budgets, lifecycle diagnostics | Implemented; dedicated tests where present | Post-M15 commits; no consolidated live regression artifact for this combination | `src/agent_platform/worker/`; `docs/evidence/post-m15-engineering-changes.md` |
| Worker self-verification and single bounded self-repair | Implemented and tested | Source-level behavior; not independent publication authority | `src/agent_platform/worker/sandbox_process.py`; `src/agent_platform/worker/self_verification.py` |
| Trusted workspace-change evidence / goal-acceptance check | Implemented and tested | Presence-of-change check only; not semantic goal satisfaction | `src/agent_platform/trust/workspace_change_evidence.py`; `src/agent_platform/trust/goal_acceptance.py` |
| Authoritative verification repair | Implemented, max **two** repair attempts after rejection; tested | Requires separate live scenario evidence for current revision | `src/agent_platform/application/supervised_coding_publication.py`; `tests/unit/test_supervised_coding_repair.py` |
| Semantic-review gate | Implemented, reject-before-publication, tested | Latest M15 recorded live run predates this gate; current live E2E not established | `src/agent_platform/adapters/workers/supervised_coding.py`; `tests/unit/test_worker_coding_semantic_review.py` |
| Persistent run history | Optional SQLite composition and tests | Configuration-dependent, not an always-on production assertion | `src/agent_platform/api/run_history_composition.py`; `tests/unit/test_sqlite_run_history_store.py` |
| GLiNER decision routing | Spike and tests | Experimental; not a required Model Gateway or default routing path | `src/agent_platform/adapters/models/gliner_decide.py`; `scripts/demo_gliner_decision_routing.py` |
| Automatic provider failover, dynamic RBAC, multitenant control plane | Not established | Deferred | `docs/architecture.md`; `docs/reviewer-guide.md` |
| Cross-process context registry / distributed workflow scheduling | Not established | Deferred; M11 assumes process-local bindings | `docs/evidence/m11-context-aware-work-execution-results.md` |

## Evidence boundaries reviewers should preserve

1. **M15/M15.6 are historical live proofs** of a bounded self-development
   workflow; they do not prove that every later step has run successfully in
   the same composition.
2. **Worker self-verification is diagnostic** feedback within a coding session.
   **Authoritative verification** is a separate trusted gate over a proposed
   `ChangeSet`. **Semantic review** is a further independent decision before
   publication. These controls must not be conflated.
3. `GoalAcceptanceEvaluator` accepts a non-empty trusted set of changed paths;
   it does **not** verify that code satisfies a user's natural-language goal.
4. The runtime's maximum **two tool-call rounds** and the publisher's **two
   verification repair attempts** are different limits. The Worker also has a
   separate **single self-repair attempt**.
5. Optional adapters, live homelab resources, startup dependencies and configured
   endpoints should not be described as universally available.

## Reproducibility and evidence backlog

A future validation of the current composite path should record: pinned Git
revision and container images; environment/configuration minus secrets; model,
provider and prompt; task and expected acceptance; Worker self-verification;
authoritative verification; bounded repair outcomes; semantic-review decision;
exact verified/published `ChangeSet` identity; PR and CI result; human merge
state; timing and failure diagnostics. Until that evidence is committed, report
these code paths as **implemented/tested**, not newly live-validated.
