# Trusted Runtime Deployment

This directory defines the operational trust boundary for supervised
self-development.

M6 introduced the trusted publisher. M15 extends that boundary with a trusted
coding sandbox, authoritative verifier and non-root Agent Platform API.

## Security invariant

```text
agent-platform API
    |
    +-- coding.sock --------> trusted sandbox daemon ----> Docker
    |
    +-- verifier.sock ------> trusted verifier daemon ---> Docker
    |
    +-- trusted-change.sock -> trusted publisher --------> GitHub

agent-platform API -> Docker: NEVER
```

The API process must never receive Docker authority or the GitHub publisher
credential.

> Self-improvement does not imply self-governance.

## Identities

The deployment uses distinct Unix identities:

- `agent-platform` — non-root API/runtime identity;
- `agent-publisher` — trusted GitHub publication authority;
- `agent-worker` — Worker/publication IPC identity where required;
- `agent-change` — shared Unix-socket IPC group.

The `agent-platform` user may communicate with trusted services through their
Unix sockets but must not belong to the Docker group.

## Canonical systemd units

The Git-tracked deployment definitions are:

```text
deploy/trusted/agent-platform-m15-api.service
deploy/trusted/agent-platform-m15-sandbox.service
deploy/trusted/agent-platform-m15-verifier.service
deploy/trusted/agent-platform-publisher.service
```

Only the sandbox and verifier daemons own Docker authority.

The API remains non-root.

## Immutable release layout

Application releases are stored under:

```text
/opt/agent-platform/releases/m15-<git-sha>/
```

The systemd units reference:

```text
/opt/agent-platform/current
```

`current` is an operator-controlled symlink to one immutable, tested release.

Example:

```bash
ln -sfn \
  /opt/agent-platform/releases/m15-<git-sha> \
  /opt/agent-platform/current
```

Changing the symlink is a deployment action. It is not available to the Worker.

## M15 state layout

Expected controller state:

```text
/var/lib/agent-platform/
├── trusted-repo/
├── workspaces/
├── verification-workspaces/
├── tools/
└── bin/
```

RepoWise is installed outside the Agent Platform Python environment and exposed
through:

```text
/var/lib/agent-platform/bin/repowise
```

## Trusted sockets

```text
/run/agent-platform-sandbox/coding.sock
/run/agent-platform-verifier/verifier.sock
/run/agent-platform/trusted-change.sock
```

Socket access is restricted through the `agent-change` group.

## M15 environment

Runtime configuration and model credentials are loaded from:

```text
/etc/agent-platform/m15.env
```

Expected ownership and mode:

```text
root:root 0600
```

systemd reads the file before dropping privileges for the `agent-platform`
service. The API process itself does not need filesystem read access to that
file.

The publisher credential remains separate:

```text
/etc/agent-platform/publisher.env
```

It is loaded only by `agent-platform-publisher.service`.

## Pinned execution images

M15 was validated with the following immutable images.

Coding Worker:

```text
sha256:27fc10067e66f28a0644a7bcfa490f3e613e46f6b7846b456e773fbb31ffa1ee
```

Authoritative verifier:

```text
sha256:74109157bffb9adb5f04ea13f2b227c3152f098bf9609b154f1eb670198f1578
```

The coding sandbox remains:

```text
network none
read-only root filesystem
non-root Worker
cap-drop ALL
no-new-privileges
bounded CPU / memory / PIDs
16 MiB ephemeral /tmp
no Docker socket
no publisher socket
Model Gateway access only through the trusted Unix-socket relay
```

`/tmp` is explicitly executable because the pinned DeepSeek Harness runtime
loads native modules from its ephemeral cache. The mount remains `nosuid` and
`nodev`.

## Trusted coding flow

```text
Task
  ↓
developer-agent
  ↓
coding.execute
  ↓
trusted sandbox socket
  ↓
disposable Worker workspace
  ↓
ChangeSet
  ↓
authoritative verifier socket
  ↓
VerifiedChangeSet
  ↓
trusted publisher socket
  ↓
Pull Request
  ↓
Trusted CI
  ↓
Human approval / merge
```

No automatic merge authority is granted to the agent.

## Publication authority

The GitHub credential is scoped to the `agent-platform` repository.

Required repository permissions:

- Contents: read/write
- Pull requests: read/write

No Actions, Workflows, Administration, Secrets, Environments or repository-wide
administrative permission is required.

## Base revision invariant

Publication is accepted only when:

```text
ChangeSet.base_revision == remote/base_branch HEAD
```

For the current deployment:

```text
ChangeSet.base_revision == origin/main HEAD
```

The exact ChangeSet that passes authoritative verification is the ChangeSet sent
to the trusted publisher.

## Protected deployment

The trusted deployment definition is part of the trust root.

At minimum:

```text
deploy/trusted/**
```

must remain protected by `ChangePolicy`.

A Worker must not be able to change:

- trusted Unix identities;
- Docker authority;
- filesystem permissions;
- trusted runtime binaries;
- credential sources;
- trusted sockets;
- verifier configuration;
- publisher configuration;
- deployment unit files.

## Concurrency

Trusted publication remains serialized.

The current mechanism intentionally avoids queues, brokers or distributed locks
until evidence requires them.

## Known limitation

The publisher workspace remains shared mutable state and can remain on the
branch created by a successful publication until reset.

This does not change the trust decision model, but disposable/resettable
publication state remains a future hardening item.

## Security property

For any Worker Agent execution, no action available to the Worker can modify,
replace, disable or bypass the gates deciding promotion of its own change.
