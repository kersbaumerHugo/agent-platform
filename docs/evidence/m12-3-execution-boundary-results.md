# M12.3 — Workspace and Execution Boundary Results

- Status: PASS
- Date: 2026-09-18
- Related ADR: ADR-0010 — Supervised Coding Work V0
- Baseline Agent Platform revision: `f3fa69a9e2eecbd34a3fa92b07878f93842471ee`
- Infrastructure companion: `kersbaumerHugo/homelab` PR #15

## Objective

Determine whether the existing supervised Worker process boundary is sufficient
for model-controlled coding execution, and if not, identify the smallest stronger
boundary that satisfies the M12 V0 requirements.

The experiment intentionally evaluates enforcement outside the model prompt.

## Baseline A — supervised subprocess

The current baseline was:

```text
SubprocessWorkerExecutor
+ disposable workspace
+ current host filesystem permissions
+ explicit process environment
+ hard timeout / process-group termination
```

Machine-readable evidence:

```text
docs/evidence/artifacts/m12-worker-boundary-baseline.json
```

Observed result:

```text
baseline_accepted = false
decision = stronger_execution_boundary_required
```

The subprocess successfully enforced a hard timeout, but did not provide an
execution security boundary.

Observed violations:

```text
outside-workspace read       allowed
outside-workspace write      allowed
forbidden environment value  visible
arbitrary Unix socket        reachable
host TCP loopback            reachable
```

Conclusion:

> `cwd`, a disposable workspace, a sanitized prompt, and subprocess supervision
> are useful lifecycle controls but are not sufficient filesystem/network
> confinement for untrusted coding execution.

`SubprocessWorkerExecutor` remains useful as a process lifecycle mechanism, but
must not be treated as the M12 coding security boundary.

## Infrastructure prerequisite

The stronger-boundary experiment required an execution host with a container
runtime.

The homelab companion change registered and reconciled:

```text
pve01
└── CT 102 / agent01
    ├── Debian 13
    ├── unprivileged LXC
    ├── nesting=1
    ├── keyctl=1
    └── Docker Engine 29.8.1
```

The non-secret desired state and verification are maintained in the homelab
repository.

The infrastructure PR explicitly does not make the Agent Platform security
decision. It only provides the runtime prerequisite.

## Candidate B — hardened Docker container

The candidate policy tested on `agent01` was:

```text
network                  none
root filesystem          read-only
workspace                one explicit RW bind mount
UID/GID                  65532:65532
Linux capabilities       drop ALL
no-new-privileges        enabled
Docker socket            not mounted
PID limit                64
memory limit             256 MiB
CPU limit                1 CPU
temporary filesystem     bounded /tmp tmpfs
container lifecycle      --rm + explicit timeout cleanup
```

Machine-readable evidence:

```text
docs/evidence/artifacts/m12-hardened-container-boundary-v0.json
```

Observed result:

```text
candidate_accepted = true
decision = hardened_container_sufficient_for_m12_v0
```

## Boundary evidence

The final candidate proved:

```text
workspace write                 ALLOWED
outside-workspace read          BLOCKED
outside-workspace write         BLOCKED
symlink escape read             BLOCKED
forbidden inherited env         BLOCKED
arbitrary Unix socket           BLOCKED
host TCP loopback               BLOCKED
Internet egress                 BLOCKED
Docker socket                   ABSENT
container rootfs write          BLOCKED
```

Privilege/resource controls proved:

```text
UID/GID                         65532:65532
effective capabilities          0
no-new-privileges               enabled
PID limit                       enforced
memory limit                    enforced
CPU limit                       enforced
```

Lifecycle cleanup proved:

```text
normal success                  observed + container cleaned
non-zero failure                observed + container cleaned
hard timeout                    enforced + container cleaned
```

No raw secret value or raw host-file content is included in either evidence
artifact.

## Workspace ownership finding

The first hardened-container candidate run failed only because the host-created
workspace was not writable by the non-root sandbox identity.

The corrected setup explicitly prepares the disposable workspace for the sandbox
UID/GID before mounting it RW.

This is an execution-boundary requirement, not a relaxation:

```text
controller creates workspace
-> controller assigns sandbox ownership
-> container receives only that workspace RW
-> container remains non-root
```

The final candidate passed after this requirement was made explicit.

## Decision

For M12 supervised coding V0:

```text
plain subprocess                    REJECTED as security boundary
hardened Docker container           PROMOTED as boundary candidate
Docker Sandboxes / microVM          DEFERRED
```

A microVM did not earn its additional operational complexity for the measured M12
V0 threat model because the hardened container satisfied every boundary property
tested.

This decision does not claim VM-equivalent isolation.

The accepted topology is intentionally layered:

```text
Proxmox host
└── unprivileged LXC agent01
    └── hardened Docker container
        └── model-controlled coding execution
```

## Separation of responsibilities

The `homelab` repository owns:

```text
agent01 existence
LXC desired state
Docker Engine installation/version
runtime health
```

The `agent-platform` repository owns:

```text
per-execution sandbox policy
workspace mount/ownership
process/resource limits
network capability
environment allowlist
container cleanup
coding execution semantics
```

This prevents infrastructure provisioning from becoming the Agent Platform's
runtime authorization policy.

## M12.4 handoff

M12.3 intentionally proves the strongest deny baseline using:

```text
--network none
```

A real DSH coding Worker must reach the platform Model Gateway.

Therefore M12.4 must define and prove the minimal coding capability envelope,
including a network path that permits only the required platform endpoint(s)
while preserving the boundary demonstrated here.

M12.4 must not replace the measured controls with prompt-only restrictions.

## M12.3 gate result

All M12.3 evidence requirements are satisfied:

```text
baseline measured                        PASS
baseline insufficiency demonstrated      PASS
stronger candidate measured              PASS
host filesystem confinement              PASS
symlink escape confinement               PASS
environment isolation                    PASS
socket isolation                         PASS
network deny baseline                    PASS
privilege controls                       PASS
resource limits                          PASS
cleanup after success                    PASS
cleanup after failure                    PASS
cleanup after hard timeout               PASS
machine-readable evidence                PASS
raw secret/content exclusion             PASS
```

M12.3 is ready to close after repository quality gates and PR review.

> Complexity must earn its place.
