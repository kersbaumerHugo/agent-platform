# Post-M15 engineering changes — source and evidence reconciliation

> Documentation inventory, 2026-10-26. Code HEAD: `2cefa5c5292459df9020eab2c6bd2324924fbd64`
> (2026-10-07), before the documentation-only merge at `7279667b`.
> This is **not** a new live experiment or an invented milestone acceptance.

## Context

The accepted [M15/M15.6 report](m15-trusted-developer-agent-results.md)
records real supervised self-development, including PR #84 and PR #89, CI,
and human-controlled merges. The later H0C/H0D work and October changes added
controls to make agent-driven coding more bounded and diagnosable. The source
and Git history document their implementation; there is no single consolidated
live result proving that the entire final combination is reliable.

## Engineering change map

| Sequence | Implementation direction | Representative source / Git history | Claim level |
| --- | --- | --- | --- |
| 2026-09-29, H0C | Prevent repeated terminal `coding_execute`, finalize tool execution | `src/agent_platform/adapters/runtimes/tool_calling.py`; PRs #132–133 | Implemented; repository commits/tests |
| 2026-09-29, H0D | DSH lifecycle metadata, prune large tool results, phase-aware model budget | `src/agent_platform/worker/dsh_lifecycle.py`; `src/agent_platform/worker/execution_budget.py`; PRs #134–139 | Implemented; do not infer universal performance gain |
| 2026-09-30, H0D | Workspace hygiene, plan-first execution, bounded self-repair, reuse DSH runtime | `src/agent_platform/worker/sandbox_process.py`; `src/agent_platform/worker/workspace_hygiene.py`; PRs #136–145 | Implemented with dedicated controls and test coverage |
| 2026-10-01–02, H0D | Self-verification evidence, recovery from hygiene failures, process budgets, isolated diagnostic verification | `src/agent_platform/worker/self_verification.py`; `src/agent_platform/trust/diagnostic_verification.py`; PRs #146–151 | Implemented; a diagnostic verifier is not the authoritative publisher gate |
| 2026-10-05, H0E/H0F | Trusted workspace evidence and a basic goal-acceptance check | `src/agent_platform/trust/workspace_change_evidence.py`; `src/agent_platform/trust/goal_acceptance.py`; PRs #152–153 | Implemented; acceptance currently checks non-empty changed paths only |
| 2026-10-05 | Bounded verification-repair feedback, final diagnostics, tool registry observability | `src/agent_platform/application/supervised_coding_publication.py`; PRs #160–164 | Implemented and covered by targeted tests |
| 2026-10-05–07 | Semantic review gate and dedicated execution mode | `src/agent_platform/adapters/workers/supervised_coding.py`; `src/agent_platform/trust/sandbox_execution.py`; PRs #165–166 | Implemented and tested; no newer full live E2E artifact recorded |
| 2026-10-05 | Local decision-routing spike using GLiNER2.5-Decide | `src/agent_platform/adapters/models/gliner_decide.py`; `scripts/demo_gliner_decision_routing.py`; PR #154 | Experiment; not automatically part of the active model routing path |
| Post-M15 repository | Optional persistent SQLite run history | `src/agent_platform/api/run_history_composition.py`; relevant tests | Implemented but requires configuration; not universal deployment state |

PR numbers are historical repository references, not fresh acceptance
certificates. For exact changed files and tests, inspect each GitHub PR and the
current `src/`/`tests/` tree.

## Three separate feedback and verification loops

**A. Inside the coding Worker:** constrained implementation, deterministic
workspace hygiene, diagnostic self-verification, and at most **one** bounded
self-repair. This helps improve candidates, but the model remains untrusted.

**B. Trusted authoritative verification:** evaluate the proposed ChangeSet
under an independent profile. If rejected, `SupervisedCodingPublicationService`
may request at most **two** distinct repairs, re-checking the exact candidate.
Failures after this limit do not publish.

**C. Semantic review before publication:** a separately configured read-only
reviewer examines the mechanically verified candidate, returns a structured
approve/reject decision, and must not change the workspace. Reject, malformed
result or workspace mutation halts the publication path. An approval is not a
proof of correctness; the publisher independently requires matching identity.

Do **not** confuse these attempts with the `ToolCallingRuntime` limit of **two
model tool-call rounds** used to coordinate agent tools.

## Reproducibility concerns reviewers should probe

1. How do base revision, exact `ChangeSet` and verified identity remain stable
   across Worker self-repair, authoritative repair and publication?
2. Is the semantic reviewer sufficiently isolated and reproducible, and can a
   model judge correctness reliably without external ground truth?
3. What operational overhead is introduced by separate DSH instances, sockets,
   verification images and multiple execution phases?
4. Which failures can be diagnosed using public trace/metric artifacts without
   logging private prompts or source content?
5. Which components could be removed while preserving the first usable
   end-to-end development capability?

## What is still missing as measured evidence

A new accepted smoke must start from a pinned source revision; execute a real
coding task through the **current** Worker and reviewer composition; record
all verification attempts, bounded repair decisions, review result and exact
published identity; include CI/human promotion and elapsed-time breakdown;
and document failure injections (bad candidate, rejected review, modified
workspace, stale base). Do not mark such a smoke PASS until it is actually run.

The governing design policy remains
[ADR-0002](../adr/0002-evidence-gated-architecture.md): **Complexity Must Earn Its Place**.
