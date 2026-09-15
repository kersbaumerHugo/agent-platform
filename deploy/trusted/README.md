# Trusted Publisher Deployment

This directory defines the operational trust boundary used by M6 self-development.

## Identities

The trusted publisher and Worker run under separate Unix identities:

- `agent-publisher`
- `agent-worker`
- shared IPC group: `agent-change`

The Worker may access the Unix socket but must not access the publisher state, runtime, workspace, or GitHub credential.

## Trusted state

Expected layout:

```text
/var/lib/agent-platform-publisher/
├── repo/       # trusted runtime source
├── venv/       # trusted runtime environment
└── workspaces/ # parent for ephemeral publication-* workspaces
```

`/var/lib/agent-platform-publisher` is owned by `agent-publisher` and mode `0700`.

## Credential

The GitHub credential lives outside Git:

```text
/etc/agent-platform/publisher.env
```

Expected ownership and mode:

```text
root:root 0600
```

The file is loaded only by `agent-platform-publisher.service`.

The Worker must not receive this credential.

## IPC

The publisher exposes:

```text
/run/agent-platform/trusted-change.sock
```

The socket is accessible to group `agent-change`.

A Worker may submit a versioned `ChangeSet` request through this socket but cannot directly mutate the trusted workspace or publication mechanism.

## Publication model

```text
Worker
  ↓
ChangeSet v1 JSON
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
GitHubPullRequestClient
  ↓
Pull Request
  ↓
Trusted CI gates
  ↓
AWAITING_APPROVAL
```

No auto-merge is introduced in M6.

## GitHub authority

The trusted GitHub credential is scoped to the `agent-platform` repository.

Required repository permissions:

- Contents: read/write
- Pull requests: read/write

No Actions, Workflows, Administration, Secrets, Environments, or repository-wide administrative permission is required.

GitHub rulesets remain an independent remote enforcement layer. The default branch ruleset requires pull requests and the following status checks:

- Syntax
- Lint
- Typecheck
- Tests
- Package

No bypass actor is configured.

## Base revision invariant

A publication request is accepted for remote publication only when:

```text
ChangeSet.base_revision == remote/base_branch HEAD
```

For the current deployment:

```text
ChangeSet.base_revision == origin/main HEAD
```

This prevents an apparently safe `ChangeSet` from inheriting unpublished local changes to protected or trusted paths.

## Concurrency

Publication is serialized inside the trusted handler.

The current implementation intentionally allows only one publication to mutate the trusted Git workspace at a time. This is the minimum mechanism required for the current shared mutable workspace.

A queue, broker, or distributed lock is not introduced without evidence that the current mechanism is insufficient.

## Protected deployment

The trusted deployment definition is part of the trust root and must be protected by `ChangePolicy`.

At minimum:

```text
deploy/trusted/**
```

must be rejected when proposed by the Worker.

Changing trusted deployment files can alter:

- the Unix identity executing the publisher;
- filesystem permissions;
- network capability;
- the trusted runtime binary;
- the credential source;
- writable filesystem locations;
- the IPC boundary.

## Current known limitation

The publication workspace is currently mutable and remains on the branch created by a successful publication until it is reset.

The next planned hardening step is a disposable or resettable workspace per publication request.

This limitation does not change the trust decision model, but it must be removed before treating repeated autonomous publication as production-ready.

## Security property

> Self-improvement does not imply self-governance.

A Worker may propose changes to the platform but cannot modify or bypass the mechanisms that decide whether its own changes are acceptable.

The intended invariant is:

> For any Worker Agent execution, no action available to the Worker can modify, replace, disable, or bypass the gates deciding promotion of its own change.
