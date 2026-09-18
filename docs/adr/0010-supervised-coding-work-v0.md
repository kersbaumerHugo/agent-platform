# ADR-0010: Supervised Coding Work V0

- Status: Proposed
- Date: 2026-09-18
- Governing principle: ADR-0002 — Evidence-Gated Architecture
- Related decisions:
  - ADR-0001 — Tool capabilities behind a platform-owned contract
  - ADR-0004 — Trusted Self-Development Boundary
  - ADR-0006 — Evaluation Plane / Eval-as-Code
  - ADR-0007 — Work API and Deterministic Orchestrator V0
  - ADR-0009 — Context-Aware Work Execution V0

## Trigger

The platform now has two previously independent capabilities:

```text
M6
untrusted coding Worker
-> disposable Git workspace
-> ChangeSet
-> Trusted Publisher
-> GitHub PR
-> Trusted CI
-> human promotion

M11
Work
-> context preparation
-> Run
-> DSH Runtime
-> Model Gateway
-> real model execution
```

The missing capability is a platform-owned, supervised coding use case that lets a
human submit a development task and receive a reviewable pull request without
granting the coding model publication or merge authority.

The target user experience is approximately:

```text
"Implement X, run the required verification, and open a PR."
```

M12 tests whether the existing Worker and trusted publication boundaries can be
composed into that capability without weakening M6 or introducing unnecessary
workflow infrastructure.

## Core security invariant

M12 preserves:

```text
Coding Agent
!= Verification Authority
!= Publication Authority
!= Merge Authority
```

The model may propose code.

The model does not define the authoritative verification profile, does not own
publication credentials, does not merge, and does not decide whether its own
change is acceptable.

Self-development remains proposal generation, not self-governance.

## Problem statement

The current Worker can modify a disposable repository workspace and produce a
`ChangeSet`, and the trusted publication boundary can publish accepted changes as
a pull request.

However, the current capability is not yet a complete supervised coding product
boundary.

M12 must add the missing integration and security guarantees:

```text
human coding task
-> canonical platform request
-> constrained coding execution
-> ChangeSet
-> platform-owned verification
-> trusted publication
-> PR
-> human merge
```

The integration must not collapse:

```text
Coding Task != Worker Runtime
Worker Runtime != Verification Authority
Verification Authority != Publisher
Publisher != Merge Authority
```

## Accepted baseline

M12 starts from these accepted or already implemented facts.

### Worker execution

The current self-development Worker already has:

```text
WorkerDevelopmentTask
WorkerDevelopmentSession
DshWorkerExecutor
DshSubprocessWorkerExecutor
DisposableWorkerWorkspace
ChangeSetBuilder
WorkerProposalRunner
```

The DSH Worker is instructed to operate inside its current workspace, implement
the requested change, run useful local checks, and avoid commit/push/PR actions.

That prompt is useful behavior guidance.

It is **not** a security boundary.

### Disposable workspace

Each Worker execution receives a fresh clone and the workspace is deleted after
the session.

The `ChangeSetBuilder` rejects path escapes, symlink upserts, non-regular changed
files, non-UTF-8 changed files, unsupported Git change states, and empty changes.

These properties constrain what can be represented in a proposed `ChangeSet`.

They do not by themselves prove that arbitrary commands executed by the coding
model cannot read or modify host resources outside the workspace.

### Trusted publication boundary

ADR-0004 already separates the Worker from publication authority.

The Worker does not receive the GitHub publication credential and cannot merge.

The trusted publisher enforces protected paths and the remote baseline invariant,
then creates a branch and pull request. Human approval remains the final promotion
authority.

M12 must reuse this boundary rather than reimplement publication inside the coding
agent.

### Model path

The Worker already routes model requests through the platform Model Gateway.

M12 does not need a new provider abstraction.

## Current security gap

A disposable working directory is not equivalent to an execution sandbox.

A prompt saying:

```text
Operate only inside the current workspace.
```

does not prevent a sufficiently capable or compromised coding process from
attempting:

```text
readable host-file access
writes outside the workspace
publisher-socket access
arbitrary network egress
credential discovery
process spawning outside intended limits
resource exhaustion
```

Therefore M12 may not claim a secure coding boundary based only on prompt
instructions or `cwd`.

M12 must produce enforcement evidence outside the model.

## Leading architecture hypothesis

The leading hypothesis is a platform-owned supervised coding application
boundary that composes the existing Worker with an explicit constrained execution
boundary, authoritative verification, and the existing trusted publisher.

Conceptually:

```text
Human
  |
  v
Coding Task
  |
  v
Supervised Coding Application Service
  |
  +--> trusted target-repository configuration
  |
  v
Disposable Workspace
  |
  v
Constrained Coding Executor
  |
  v
DSH Coding Worker
  |
  v
ChangeSet
  |
  v
Authoritative Verification
  |
  +--> PASS -> Trusted Publisher -> PR -> Trusted CI -> Human Merge
  |
  +--> FAIL -> no publication
```

The exact public API and class names are not fixed by M12.0.

## Integration strategies

### Strategy A — expose `WorkerDevelopmentTask` directly

Conceptually:

```text
API
-> WorkerDevelopmentTask
-> WorkerProposalRunner
```

Advantages:

- minimal implementation;
- maximally reuses current code.

Costs:

- exposes a Worker-specific internal model as the platform contract;
- has no explicit authoritative verification boundary;
- risks treating prompt/cwd behavior as sufficient confinement;
- couples the public coding capability to the current Worker implementation.

Strategy A is the simplicity baseline.

It must not be promoted if it cannot satisfy M12 security properties.

### Strategy B — platform-owned Coding Task boundary

Conceptually:

```text
CodingTask
-> SupervisedCodingService
-> Worker adapter
-> ChangeSet
-> Verification policy
-> Trusted Publisher
```

Advantages:

- keeps the user-facing contract platform-owned;
- preserves Worker replaceability;
- creates an explicit place for security policy and verification;
- reuses M6 publication instead of granting publication to the model;
- allows later reuse by another coding runtime.

Costs:

- introduces a small application boundary and result model;
- requires explicit correlation across task, execution, verification, and PR.

Strategy B is the leading hypothesis.

### Strategy C — represent coding only as a generic WorkStep

Conceptually:

```text
/work
-> generic WorkStep
-> agent with shell/filesystem tools
```

Advantages:

- reuses the generic Work API.

Costs:

- generic Work semantics do not currently express authoritative code verification,
  ChangeSet publication, protected-path policy, or PR outcome;
- publication behavior would become implicit agent behavior;
- security authority would be harder to distinguish from task execution.

M12 may reuse Work/Run primitives where they fit, but must not force coding
publication semantics into generic Work solely for API uniformity.

### Strategy D — workflow engine / autonomous development platform

A queue, DAG engine, scheduler, autonomous retry system, multi-agent review loop,
or long-running development branch is not justified by the current supervised
goal.

Strategy D is out of scope for M12 V0.

## Trust zones

M12 distinguishes four authorities.

### Zone U — untrusted coding execution

Contains:

```text
LLM / DSH coding process
workspace contents
commands started by the coding process
code and tests authored by the coding process
```

This zone must not receive:

```text
GitHub publication credential
merge authority
trusted verification configuration mutation authority
trusted publisher filesystem access
arbitrary host filesystem access
```

### Zone C — platform coding controller

Owns:

```text
task lifecycle
workspace creation
execution limits
ChangeSet construction
correlation IDs
decision to invoke verification
decision to submit a verified proposal
```

It must still not own GitHub merge authority.

### Zone V — authoritative verification

The authoritative verification profile is platform-owned, not model-owned.

The coding Worker may run checks for feedback, but those checks are advisory.

Acceptance verification must be executed independently from the model's
self-report.

Because verification executes untrusted code and tests, the verification executor
must itself run without publisher credentials and with an execution boundary
appropriate for untrusted code.

The verification controller may be trusted to select the immutable verification
profile while its command executor remains isolated.

### Zone P/H — publication and promotion

The trusted publisher owns publication authority.

GitHub CI is an independent gate.

The human owns merge/promotion authority.

No M12 path may auto-merge to `main`.

## Execution-confinement decision rule

M12 does not pre-select a sandbox product merely because one is available.

The current baseline is measured first.

Eligible enforcement approaches include:

```text
hardened OS/process isolation
container/microVM sandbox backend
another demonstrably equivalent execution boundary
```

A prompt-only restriction is not eligible.

If the current Unix/process boundary cannot prove the required filesystem,
credential, socket, network, and resource isolation, then an execution sandbox
has earned its place.

Docker Sandboxes (`sbx`) remains a strong candidate, but M12 must promote it only
from measured evidence.

## Capability policy

M12 V0 needs a coding capability policy, but it should express authority rather
than rely only on brittle command-string blacklists.

The coding executor should have only capabilities required for the task, such as:

```text
read/write the disposable workspace
execute build/test tooling inside the execution boundary
access the configured Model Gateway
```

It should not have effective capability to:

```text
push to GitHub
merge
read publisher credentials
modify trusted publisher state
connect to the trusted publication socket from model-controlled execution
write arbitrary host paths
use unrestricted network egress
gain privilege
```

A future general-purpose policy engine is not assumed.

## Repository target

For V0, the repository target is trusted configuration.

The model must not be able to turn an arbitrary repository URL, local path, or
base branch into a trusted publication target.

A future multi-repository registry may be introduced only when needed.

## Branch and promotion semantics

M12 is supervised.

The expected publication shape is:

```text
main
  ^
  |
human-approved PR
  |
task branch
```

One supervised coding task produces at most one proposal PR.

The autonomous-development topology:

```text
agent/*
-> dev
-> human-selected promotion
-> main
```

is explicitly deferred.

M12 must not create or depend on a long-lived `dev` branch.

## Authoritative verification

The model's own statement:

```text
"tests passed"
```

is never sufficient evidence.

M12 must define a platform-owned verification profile.

For the Agent Platform repository, the expected baseline is:

```bash
python -m compileall -q src tests scripts
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m mypy src
python -m pytest -q
python -m build
git diff --check
```

The exact profile representation is an M12 experiment detail.

Required properties:

- the coding model cannot modify which checks are authoritative;
- verification failure blocks publication;
- verifier output is bounded and sanitized for evidence;
- verification runs without publication credentials;
- the same ChangeSet that is verified is the one submitted for publication.

## Change integrity

M12 must preserve a stable relationship between:

```text
trusted base revision
ChangeSet hash
verification result
published proposal
```

A verified ChangeSet must not be silently replaced or mutated before publication.

The existing remote baseline invariant remains mandatory.

If the remote base moves before publication, the proposal must fail closed or be
re-created and re-verified; M12 must not silently publish against a different
baseline.

## Failure semantics

Required fail-closed behavior includes:

```text
coding execution fails
-> no publication

coding execution times out
-> terminate execution
-> clean workspace
-> no publication

execution-boundary violation
-> terminate/fail
-> no publication

ChangeSet invalid
-> no verification/publication

protected path modified
-> rejected by trusted boundary

authoritative verification fails
-> no publication

base revision mismatch
-> no publication

publisher rejects
-> task returns rejected/failed publication state

PR creation succeeds
-> task ends awaiting human review
```

Automatic retry is not part of V0.

## Evidence and observability

M12 should correlate:

```text
coding_task_id
execution/run identifier
base revision
ChangeSet hash
changed paths
verification profile/version
verification result
publication request
PR number
```

Default telemetry must not include:

```text
repository credentials
publisher credentials
raw environment
raw model prompts
raw command output without explicit evidence policy
secret-bearing file contents
```

Source-code content should not be duplicated into telemetry merely because it is
present in the ChangeSet.

## Evaluation

ADR-0006 applies.

Required deterministic cases include at least:

```text
allowed code change succeeds
no-change proposal fails
path escape rejected
symlink escape rejected
protected path rejected
coding timeout cleans workspace
coding process cannot obtain publisher credential
coding process cannot use publication authority
authoritative verification failure blocks publication
base revision mismatch fails closed
verified ChangeSet identity is preserved to publication
successful proposal produces one PR result
```

Execution-confinement probes must also test the properties M12 claims.

## Success criteria

ADR-0010 may be accepted only if M12 demonstrates:

1. a platform-owned supervised coding task can invoke the coding Worker;
2. the coding Worker operates only on a disposable repository workspace;
3. workspace confinement is enforced outside the prompt;
4. model-controlled execution cannot read publisher credentials;
5. model-controlled execution cannot publish or merge;
6. model-controlled execution cannot connect directly to trusted publication
   authority;
7. effective host filesystem access is limited to the accepted boundary;
8. network egress is limited to what the coding execution requires;
9. execution has bounded lifetime and cleanup on success/failure;
10. a deterministic `ChangeSet` is produced from the Worker changes;
11. protected-path policy remains independently enforced;
12. authoritative verification is platform-owned;
13. verification executes untrusted code without publication credentials;
14. verification failure prevents publication;
15. the verified ChangeSet is the one submitted for publication;
16. remote/base revision mismatch fails closed;
17. successful publication creates a PR and never auto-merges;
18. GitHub CI remains an independent gate;
19. human approval remains final promotion authority;
20. machine-readable Eval-as-Code and integration evidence pass;
21. a supervised real coding task produces a real reviewable PR;
22. no queue, scheduler, workflow engine, autonomous retry system, or `dev` branch
    is required for V0.

## Guardrails

M12 must not:

- expose GitHub publication credentials to the coding model;
- let the coding model merge;
- let the coding model redefine the authoritative verification profile;
- treat Worker-run tests as authoritative acceptance evidence;
- run untrusted verification under the publisher credential boundary;
- consider `cwd` or a prompt to be filesystem confinement;
- silently publish an unverified or differently based ChangeSet;
- bypass ADR-0004 protected paths;
- move publication logic into DSH;
- make DSH the platform's coding contract;
- introduce a general workflow engine for one supervised coding task;
- create the future autonomous `dev` branch as part of M12;
- auto-promote agent changes to `main`.

## Explicitly deferred

M12 V0 does not require:

```text
autonomous recurring coding
long-lived dev integration branch
agent/* -> dev auto-merge
automatic dev -> main promotion
multi-agent planner / reviewer swarm
automatic retry
issue polling
queue
scheduler
DAG orchestration
cross-repository development
automatic dependency upgrades
internet-browsing coding agent
self-modification of trusted gates
self-modification of publisher policy
automatic merge
```

## Experiment

This ADR remains **Proposed** until the experiment in:

```text
docs/evidence/m12-supervised-coding-work-experiment-plan.md
```

is completed.

Expected results should be recorded in:

```text
docs/evidence/m12-supervised-coding-work-results.md
```

## Decision rule

After the experiment:

- **Accepted** if a human-requested coding task can safely reach a real PR while
  preserving independent execution, verification, publication, and merge
  authorities.
- **Deferred** if the integration works functionally but execution confinement or
  verification authority cannot yet be proven.
- **Rejected** if supervised coding requires collapsing the M6 trust boundary or
  adds more infrastructure than the current goal justifies.

The governing rule remains:

> Complexity must earn its place.
