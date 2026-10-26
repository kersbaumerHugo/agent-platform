# Architecture as built — Agent Platform

> Snapshot: 2026-10-26, `main` at `7279667b9790205002c22a663e07aa2cb0ff0d1d`.
> Current-code architecture overview. Historical decisions remain in the ADRs;
> accepted experiments remain in `docs/evidence/`. See
> [capability status](capability-status.md) for claim-by-claim evidence levels.

## Scope and boundaries

The platform owns runtime, model, tool/capability, context and verification
contracts. An agent owns its task and model decisions; neither model-generated
code nor an agent's success report becomes trusted publication authority.

The API's runtime composition is **configuration-driven**:

```text
                        FastAPI
                POST /runs   POST /work
                     |         |
                     v         v
                  RunAgent <- WorkOrchestrator
                     |        (sequential, fail-fast)
                     |                 |
                     |        optional selected-context preparation
                     |                 |
                     +------ Run-scoped context binding (process-local)
                     |
                     v
           RuntimeContract (explicit selection)
            |               |                |
         FakeRuntime      DSHRuntime     ToolCallingRuntime
                                           |             |
                                           v             v
                                       ModelGateway  ToolRegistry
                                           |          + authorization
                                    OpenRouter /       + typed capabilities
                                    local OpenAI       + RepoWise inspection
                                    compatible        + optional coding
```

Without `AGENT_PLATFORM_RUNTIME`, the API builds `FakeRuntime`. Real
`tool-calling` or `dsh` must be explicitly configured; booting FastAPI does not
by itself verify an agentic run.

The OpenAI-compatible *internal* gateway and MCP *protocol adapter* are distinct
interfaces. A platform-native typed capability need not traverse MCP; external
runtimes can consume MCP. The Model Gateway does not make model providers or
runtimes universally interchangeable without compatibility testing.

## Context-aware Work execution (M11)

```text
WorkRequest(objective, explicit ContextRef[], ordered steps)
    -> WorkOrchestrator
    -> PrepareContext, when configured and requested
    -> deterministic retrieval / ACCEPT-ABSTAIN / assembly / budget
    -> RunAgent (allocates run_id)
    -> in-process run_id -> prepared-context binding
    -> runtime + internal Model Gateway
    -> reference-message injection into ModelRequest
    -> model response; release binding on success/failure
```

Prepared context does not become a new system instruction. A context-dependent
Work step fails closed if preparation is unavailable. The binding is **not**
shared across independent API/Gateway processes or hosts. M11 recorded real
DSH paths using OpenRouter and local inference; M14 independently recorded a
repository-aware `ToolCallingRuntime` path.

## Supervised coding — current source composition

```text
Human task / developer-agent
       |
       v
ToolCallingRuntime (at most two model tool-call rounds)
       |
       +--> repository_inspect: RepoWise evidence + exact revision
       |
       +--> coding_execute: explicit authorized capability
                   |
                   v
         SupervisedCodingService
                   |
            disposable workspace
                   |
       trusted sandbox (coding Worker)
                   |
           Worker-level iteration
           - planning / constrained model-call budget
           - workspace hygiene
           - diagnostic self-verification
           - at most one Worker self-repair
                   |
          trusted workspace evidence
          + presence-of-change acceptance
                   |
               ChangeSet
                   |
     trusted authoritative verifier
          | PASS             | REJECT
          |                  v
          |            optional repair producer
          |            (max two repair attempts)
          |                  |
          +<-----------------+ re-verify
                   |
              VerifiedChangeSet
                   |
           semantic review in dedicated
           read-only execution mode
             | APPROVE    | REJECT / invalid / mutation
             |            +--> stop, no publication
             v
       trusted publication authority
       (identity must match verified ChangeSet)
                   |
                GitHub PR
                   |
         repository CI + human merge
```

This is a composite of implementation paths, **not a claim** that every stage
has been exercised in the latest live stack. M15/M15.6 demonstrated a real
inspect/code/verify/PR/human-merge route. The current semantic-review and
verification-repair layers have implementation/tests but lack a new consolidated
live acceptance report. A successful tool return cannot grant auto-merge.

## Trust zones and invariants

| Zone | Authority | What it must not do |
| --- | --- | --- |
| Model/runtime and coding Worker | Inspect, propose code, emit untrusted change candidate | Possess publisher token; approve its own merge; alter trusted controls |
| Trusted sandbox service | Own Docker execution boundary and lifecycle | Give API or Worker ambient Docker authority |
| Authoritative verifier | Verify an exact candidate in a separate trusted boundary | Accept model self-report as authoritative; rewrite candidate silently |
| Semantic reviewer | Inspect mechanically verified candidate and return a bounded decision | Mutate reviewed workspace; grant publication by bypassing authoritative verifier |
| Trusted publisher | Enforce policy, exact revision/identity and create a PR | Merge automatically on behalf of the agent |
| GitHub CI and human reviewer | Independently gate promotion | Equate a green build with general correctness/security |

The `agent_id` supplied by a request does **not** grant permission. The
composition owns the authorization principal and explicit grants. The API
itself should not gain Docker authority or publisher credentials. Trusted
socket permissions and deployment details are in
[`deploy/trusted/README.md`](../deploy/trusted/README.md).

**Important semantic distinction:** the current `GoalAcceptanceEvaluator`
checks for a non-empty set of changed paths; it does **not** demonstrate that
the requested functionality actually works. Semantic review is also a model
judgment, not a proof of correctness.

## Failure and recovery semantics

- Tool-call round limit: **two**, then fail closed if more tool use is requested.
- Worker diagnostic self-repair: **one** bounded attempt within its execution.
- Authoritative verification-repair: **two** further attempts at most on
  verification rejection; preserve trusted base and publication metadata, and
  require a candidate change.
- Semantic review: rejection, malformed review contract or candidate mutation
  fails the publication path rather than silently accepting.
- Exact verified/published `ChangeSet` identity must match; base revision and
  protected path policies remain enforced outside the coding model.
- The publisher workspace is shared mutable state; operational hygiene and
  concurrency remain review points.

## Deployment and observability

The documented homelab deployment uses systemd, immutable release directories,
non-root API execution, Unix sockets for trusted services, and local model
inference. Instrumentation includes structured events, Prometheus and
OpenTelemetry; correlation by `run_id` exists, but traceparent propagation
across every process boundary is **not** established. Optional SQLite run
history is enabled only with its database and valid revision configuration.

Do not equate this local topology to cloud production, multitenancy or an
Internet-facing MCP deployment. The repository supplies a Git-tracked CI,
but its ordinary test job does not execute an actual live LLM coding session.

## Risks and evidence gaps

- Overabstraction versus a smaller vertical slice; maintaining parallel DSH,
  tool-calling and Worker compositions has a real cost.
- Known latency: M15.6 recorded roughly 529 seconds for one live task.
- No consolidated new live run proving the complete later repair + semantic
  review chain with exact verified/published identity and rollback behavior.
- Model-level prompt-injection resistance and container isolation are limited
  to tested properties, not general-purpose security guarantees.
- No public-MCP trust boundary, distributed context registry, dynamic RBAC,
  production-grade provider failover or general multitenant control plane.

For source-specific links and historical PR stages, see
[post-M15 changes](evidence/post-m15-engineering-changes.md),
[capability status](capability-status.md), and
[M15 evidence](evidence/m15-trusted-developer-agent-results.md).
