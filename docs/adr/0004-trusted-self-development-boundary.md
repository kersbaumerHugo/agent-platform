# ADR-0004: Trusted Self-Development Boundary

- **Status:** Accepted
- **Date:** 2026-09-14
- **Decision scope:** M6 — Agent Self-Development / Trusted Change Loop
- **Related:** ADR-0002 Evidence-Gated Architecture; ADR-0003 systemd + Python venv deployment

## Context

The Agent Platform is intended to eventually develop and improve its own codebase.

Allowing a Worker Agent to modify platform code introduces a fundamental trust problem: the same agent that proposes a change must not control the mechanism that decides whether that change is acceptable.

A self-developing agent therefore requires a strict separation between:

```text
Worker Agent
Trusted Publisher
Acceptance Gates
Human Promotion Authority
```

The central security requirement is:

> Self-improvement does not imply self-governance.

The Worker may propose changes to the platform, but must not be able to modify, replace, disable, or bypass the mechanisms deciding whether its own changes are acceptable.

This property is referred to as **Gate Non-Interference**.

## Decision

Adopt a separate trusted publication boundary for self-development.

The Worker and trusted publisher run under separate Unix identities and communicate only through a narrow Unix-domain socket protocol.

The Worker does not receive:

- the GitHub credential;
- direct access to the trusted publication workspace;
- direct access to the trusted runtime environment;
- authority to merge pull requests;
- authority to modify GitHub rulesets, repository secrets, Actions settings, or other administrative controls.

The trusted publisher owns publication authority.

The publication flow is:

```text
Work Item
  ↓
Worker Agent
  ↓
ChangeSet v1
  ↓
Unix socket
  ↓
TrustedChangeHandler
  ↓
ChangePolicy
  ↓
TrustedPublisher
  ↓
GitRemoteChangeSink
  ↓
PullRequestChangeSink
  ↓
GitHub PR
  ↓
Trusted CI
  ↓
AWAITING_APPROVAL
```

No auto-merge is permitted in the current M6 scope. Human approval remains the final promotion authority.

## Trust boundary

### Worker identity

Current Unix identity:

```text
agent-worker
```

The Worker is a member of the shared IPC group:

```text
agent-change
```

The Worker may connect to:

```text
/run/agent-platform/trusted-change.sock
```

The Worker must not read or write:

```text
/var/lib/agent-platform-publisher
/etc/agent-platform/publisher.env
```

### Trusted publisher identity

Current Unix identity:

```text
agent-publisher
```

The trusted publisher owns:

```text
/var/lib/agent-platform-publisher
```

and executes the trusted publication runtime.

The trusted publisher receives the GitHub credential through:

```text
/etc/agent-platform/publisher.env
```

owned by:

```text
root:root 0600
```

### IPC contract

The Worker submits a versioned JSON `ChangeSet`.

Current protocol version:

```text
version = 1
```

The trusted parser rejects malformed JSON, unsupported protocol versions, missing or unexpected fields, unsupported file operations, and invalid content types. The protocol is fail-closed.

## Change policy

`ChangePolicy` rejects attempts to modify trusted paths.

Protected paths include, at minimum:

```text
.github/**
pyproject.toml
setup.cfg
tox.ini
pytest.ini
ruff.toml
.ruff.toml
mypy.ini
.mypy.ini
conftest.py
**/conftest.py
src/agent_platform/trust/**
src/agent_platform/adapters/git/**
src/agent_platform/adapters/github/**
tests/trusted/**
deploy/trusted/**
```

The protected set includes both direct gate implementation and configuration capable of changing how gates execute.

The protected set must evolve as additional transitive gate dependencies are introduced.

## Remote baseline invariant

Remote publication is accepted only when:

```text
ChangeSet.base_revision == remote/base_branch HEAD
```

The current deployment binds publication to:

```text
origin/main
```

This prevents a Worker from proposing an apparently safe diff on top of a local commit that already contains unauthorized changes.

## Concurrency decision

The trusted publisher currently uses one mutable Git workspace. Therefore publication is serialized with an in-process `asyncio.Lock`.

This prevents concurrent requests from racing on branch creation, `HEAD`, staged changes, commits, and push state.

A broker, external queue, distributed lock, or additional service is not adopted. Per ADR-0002, additional complexity must demonstrate a concrete need.

## GitHub enforcement

The GitHub default-branch ruleset remains an independent enforcement layer.

Current protections include:

- deletion blocked;
- non-fast-forward updates blocked;
- pull request required;
- no configured bypass actor;
- required status checks: Syntax, Lint, Typecheck, Tests, Package.

The trusted adapter exposes pull-request creation but no merge operation.

The GitHub credential is repository-scoped and limited to the permissions required for branch publication and pull-request creation.

## Evidence

### Worker cannot read trusted state

As `agent-worker`:

```text
ls /var/lib/agent-platform-publisher
→ Permission denied
```

### Worker cannot write trusted state

As `agent-worker`:

```text
touch /var/lib/agent-platform-publisher/ATTACK
→ Permission denied
```

### Worker cannot execute trusted runtime

Access to the trusted virtual environment from `agent-worker` was denied by Unix filesystem permissions.

### Worker can access only the IPC boundary

The Worker successfully detected and connected to:

```text
/run/agent-platform/trusted-change.sock
```

while remaining unable to access the trusted publisher state.

### Protected change rejected end-to-end

The Worker submitted a `ChangeSet` attempting to modify:

```text
.github/workflows/ci.yml
```

The trusted publisher returned:

```text
status = rejected
reason_code = protected_path_modified
```

No Git mutation occurred.

### Allowed local publication accepted

The Worker submitted an allowed documentation change through the same socket. The trusted publisher created the commit. The Worker still could not read the trusted filesystem directly.

### GitHub credential isolation

The GitHub credential was stored outside Git in a root-owned `0600` `EnvironmentFile`. The Worker could not read the credential file or the publisher process environment.

### Remote end-to-end publication

The Worker submitted an allowed documentation change through the trusted Unix socket.

Without manual push, the trusted side:

1. validated the request;
2. verified the remote `main` baseline;
3. created a new branch;
4. committed the change;
5. pushed the branch;
6. created GitHub Pull Request #15;
7. triggered CI.

PR #15 changed only:

```text
docs/m6-remote-publication-proof.md
```

All required CI jobs passed. The PR remained unmerged and awaited human promotion.

### Trusted boundary implementation CI

The implementation branch was proposed through Pull Request #16. All required CI gates passed: Syntax, Lint, Typecheck, Tests, Package.

## Alternatives considered

### Let the Worker push directly to GitHub

Rejected. This would expose publication credentials and allow the Worker to bypass the trusted publisher boundary.

### Let the Worker modify CI and trusted tests

Rejected. This violates Gate Non-Interference by allowing the proposer to redefine its own acceptance criteria.

### Run Worker and Publisher under the same Unix identity

Rejected. Logical separation alone would not prevent the Worker from reading credentials or mutating trusted state.

### Introduce Docker, Kubernetes, a queue, or a separate distributed control plane

Not adopted. The current requirement is satisfied by Unix identities, filesystem permissions, a Unix socket, systemd, GitHub rulesets, and a narrow trusted process.

Per ADR-0002, additional infrastructure must earn its place through evidence.

## Consequences

### Positive

- Worker self-development can proceed without granting self-governance.
- GitHub credentials remain outside the Worker runtime.
- Trusted gates and deployment definitions are explicitly protected.
- Remote publication is bound to the trusted branch baseline.
- GitHub remains an independent enforcement layer.
- The architecture remains small and reproducible.
- The security property is testable end-to-end.

### Negative

- The trusted publisher becomes security-critical infrastructure.
- Protected path coverage must be maintained as the system evolves.
- The current publication workspace is mutable.
- A single in-process lock limits publication concurrency.
- Operational provisioning of users, permissions, systemd, and credential files must remain consistent with the versioned deployment definition.

## Disposable publication workspace

M6.3 resolves the mutable shared publication workspace limitation.

Each remote publication now:

1. creates a fresh `publication-*` workspace;
2. clones the trusted remote base;
3. validates the requested base revision;
4. publishes the branch;
5. removes the workspace in a `finally` path.

Cleanup is exercised for both successful and failed publication paths.

Persistent publication workspace state is no longer part of the remote publication architecture.

## Decision outcome

The Trusted Self-Development Boundary is **accepted** for M6.

The platform may proceed with self-development only while preserving:

```text
Worker ≠ Trusted Publisher ≠ Acceptance Gates ≠ Promotion Authority
```

Any future design that collapses those authorities requires a new ADR and evidence showing that Gate Non-Interference remains intact.
