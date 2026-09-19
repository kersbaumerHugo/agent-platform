# M12.4 — Coding Capability Policy V0

## Status

Accepted for M12 V0 evidence.

This milestone establishes the minimum authority required for supervised coding execution and proves that the authority can be enforced by the current homelab runtime.

## Capability contract

The coding execution is allowed to:

- read and write only its assigned workspace;
- execute processes inside the sandbox;
- use the Model Gateway through an explicit capability.

The coding execution is denied authority to:

- read or write arbitrary host filesystem paths;
- access the trusted publisher socket;
- access the Docker socket;
- access unrestricted LAN or Internet networking;
- possess publication credentials;
- push or merge directly;
- escalate process privileges.

The canonical policy is fixed by the platform and is not caller-relaxable.

## Authority separation

The M12 V0 invariant remains:

```text
Coding Agent
!= Verification Authority
!= Publication Authority
!= Merge Authority
```

Docker daemon authority is intentionally not granted to the Agent Platform API process or to the coding container. The trusted sandbox executor is the narrow authority boundary responsible for translating a minimal execution request into a fixed sandbox policy.

The caller request carries only execution intent:

```text
execution_id
workspace_name
goal
```

It does not carry image names, Docker flags, mount sources, network configuration, UID/GID choices, credentials, or publication authority.

## Evidence progression

### Baseline subprocess boundary

The existing subprocess worker provided lifecycle control and a hard timeout, but it did not provide a sufficient security boundary. The baseline probe demonstrated host filesystem access, host writes, loopback/LAN connectivity, Unix-socket connectivity, and inherited environment visibility.

That evidence justified adding a stronger sandbox boundary.

### Hardened Docker candidate

A hardened Docker container inside the unprivileged `agent01` LXC was previously shown to enforce the required process, filesystem, and resource controls for the M12 threat model:

- read-only root filesystem;
- all Linux capabilities dropped;
- `no-new-privileges`;
- non-root execution;
- CPU, memory, and PID limits;
- writable workspace only;
- temporary `/tmp`;
- no Docker socket;
- cleanup on success, failure, and timeout.

This is not claimed to be VM-equivalent isolation.

### TCP host-gateway relay rejected

A dedicated Docker `--internal` bridge prevented Internet and direct LAN access, but a follow-up probe showed that the coding container could still reach the host SSH service through the Docker bridge gateway.

Evidence: `docs/evidence/artifacts/m12-4-host-surface-probe.json`.

Because this exceeded the intended capability set, the host-gateway TCP relay design was rejected instead of compensated with a port blacklist.

### Network-none + Unix-domain socket capability

A follow-up probe used Docker `--network none` and mounted only a Unix-domain socket into the container.

The result showed:

- Model Gateway socket reachable;
- host SSH unreachable;
- Internet unreachable.

Evidence: `docs/evidence/artifacts/m12-4-uds-transport-probe.json`.

This became the selected M12 V0 transport because it expresses Model Gateway access as an explicit capability rather than as partially restricted general networking.

### Credential isolation

The trusted Unix-socket gateway relay strips caller-supplied authorization and injects the real Model Gateway bearer credential on the trusted side.

The coding container receives only a non-secret placeholder.

The live backend probe demonstrated both:

```text
gateway_auth_passed_via_uds = true
gateway_secret_is_placeholder = true
```

Therefore, for the tested boundary:

```text
Coding Agent can use Model Gateway
!=
Coding Agent possesses Model Gateway credential
```

### Live DockerSandboxBackend probe

The real backend was executed on `agent01` against Docker Engine with the fixed M12 V0 policy.

Evidence: `docs/evidence/artifacts/m12-4-docker-backend-live-boundary.json`.

The observed result was:

```text
cap_eff                         = 0000000000000000
docker_socket_visible           = false
gateway_auth_passed_via_uds     = true
gateway_secret_is_placeholder   = true
gid                             = 65532
host_ssh_reachable              = false
internet_reachable              = false
no_new_privileges               = true
publisher_socket_visible        = false
rootfs_write_allowed            = false
uid                             = 65532
workspace_write_allowed         = true
violations                      = {}
```

The candidate passed the live capability boundary.

## Selected M12 V0 boundary

```text
Agent Platform controller
        |
        | minimal Unix-socket execution request
        v
Trusted Sandbox Executor
        |
        | fixed, trusted policy
        v
Docker coding container
  --network none
  --read-only
  --cap-drop ALL
  --security-opt no-new-privileges
  --pids-limit 64
  --memory 256m
  --cpus 1
  --user non-root
  --tmpfs /tmp
        |
        +--> workspace RW
        |
        +--> Model Gateway UDS RO mount
                 |
                 v
          Trusted credential relay
                 |
                 v
            Model Gateway
```

The image is required to be pinned by SHA-256 digest or image ID. The coding goal is passed as data through stdin and cannot modify Docker authority flags.

## Residual trust and limits

This evidence supports the M12 V0 threat model; it does not establish VM-equivalent isolation.

The trusted sandbox service remains a privileged component because Docker daemon authority is effectively root-equivalent. Its production deployment must therefore keep Docker authority out of the Agent Platform API process, expose only the narrow Unix-socket execution contract, use restrictive filesystem permissions for its IPC and runtime paths, and keep the real Model Gateway credential outside the coding container.

The current evidence also assumes the trusted controller and trusted sandbox service are not maliciously racing workspace path resolution. Stronger protection against a compromised trusted controller can be evaluated separately if that threat enters scope.

No publication, push, merge, or verification authority is granted by this milestone.

## Verification

The branch-wide quality gate passed after the implementation:

```text
compileall           PASS
ruff check           PASS
ruff format --check  PASS
mypy                 PASS
pytest               PASS — 429 passed
python -m build      PASS
git diff --check     PASS
```

## Decision

Accept the hardened Docker boundary with `--network none` and an explicit Unix-domain-socket Model Gateway capability for M12 V0.

Reject the internal-bridge host-gateway TCP relay for M12 V0 because it exposed additional host network surface.

Defer stronger VM/microVM sandboxing until evidence shows the current boundary is insufficient for the defined threat model.
