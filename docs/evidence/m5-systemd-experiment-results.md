# M5 C1 Experiment Results — systemd + Python virtual environment

- Status: Completed
- Date: 2026-09-14
- Candidate: C1 — systemd + Python virtual environment
- Governing ADR: ADR-0002 — Evidence-Gated Architecture
- Experiment plan: `docs/evidence/m5-systemd-experiment-plan.md`
- Final decision: **Accepted**

## Executive summary

The M5 deployment experiment validated that the Agent Platform can be operated as
a persistent homelab workload using systemd, a Python virtual environment,
versioned release directories and host-local runtime configuration.

All experiment gates P0-P10 passed.

The candidate satisfied startup, automatic recovery, version identity,
observability, semantic invariance, roll-forward and rollback requirements
without introducing Docker, Compose, Kubernetes, K3s or another long-running
control plane.

The experiment therefore supports accepting C1 as the current deployment
architecture.

## Environment

Deployment target:

- hostname: `agent01`
- Proxmox CT: VMID 102
- operating system: Debian 13
- address: `192.168.10.30/24`
- CPU: 2 vCPU
- memory: 2048 MiB
- swap: 512 MiB
- root filesystem: 16 GiB
- startup order: 30
- workload isolation: unprivileged LXC

Supporting services:

- Tempo: `192.168.10.20:4317`
- Tempo HTTP/API: `192.168.10.20:3200`
- Model Gateway: `192.168.10.30:8000`
- MCP: `192.168.10.30:8001`

## Deployment model

Release layout:

```text
/opt/agent-platform/
├── releases/
│   ├── v0.1.1/
│   ├── 9f23961/
│   └── p10-broken/
└── current -> releases/<active-release>
```

Each normal release contains:

```text
app/
.venv/
REVISION
SOURCE_SHA256
PYTHON
DEPENDENCIES.txt
```

Runtime configuration and secrets are stored outside Git under:

```text
/etc/agent-platform/
```

Services:

```text
agent-platform-api.service
agent-platform-mcp.service
```

Both services execute through the active release symlink:

```text
/opt/agent-platform/current/.venv/bin/python -m uvicorn ...
```

## Tested revisions

Initial deployed revision:

```text
668b8c8d259bd3741b3cf029717b9d19b42cd46e
```

Roll-forward target:

```text
9f239617fe608e995c29f0c29aa5bc985c556f46
```

The active deployment after the experiment is:

```text
/opt/agent-platform/releases/9f23961
```

with:

```text
REVISION=9f239617fe608e995c29f0c29aa5bc985c556f46
```

## Phase results

### P0 — Inventory and preflight

**Result: PASS**

An isolated workload target was identified with sufficient CPU, memory, storage
and required network reachability.

No application dependencies were installed directly on the Proxmox host.

### P1 — Provision experiment target

**Result: PASS**

`agent01` was provisioned as an isolated Debian workload guest and successfully
reached the required network paths.

Tempo OTLP and monitoring-related network paths were reachable.

### P2 — Install known release

**Result: PASS**

The release was installed into a versioned release directory.

The deployment records:

- exact Git revision;
- Python version;
- resolved dependency set;
- release source checksum;
- release disk usage.

Observed release size for `v0.1.1`:

```text
110M
```

Observed release size for `9f23961`:

```text
111M
```

### P3 — Workload identity and secrets

**Result: PASS**

Runtime secrets are stored outside the repository.

Observed permissions:

```text
/etc/agent-platform/api.env  0600 root:root
/etc/agent-platform/mcp.env  0600 root:root
```

Both services load their environment through systemd and require no interactive
`source .env`.

### P4 — systemd lifecycle

**Result: PASS**

Both services were configured as enabled systemd units.

Observed state:

```text
agent-platform-api.service  active
agent-platform-mcp.service  active
```

Both remain running after the operator shell exits.

### P5 — Functional verification

**Result: PASS**

The deployed candidate preserved the validated agentic execution path:

```text
DSH
 -> Model Gateway
 -> OpenRouter
 -> model-generated tool call
 -> DSH
 -> MCP
 -> ToolRegistry
 -> DiagnosticEchoTool
 -> DSH
 -> Model Gateway
 -> OpenRouter
 -> final response
```

Successful run:

```text
run_id: 1af665ab-bcbd-4c01-821a-b68f0d86282f
output: Agent01 deployment succeeded.
```

### P6 — Observability verification

**Result: PASS**

Tool metrics were observed:

```text
agent_platform_tool_requests_total{status="succeeded",tool="diagnostic_echo"} 1.0
```

Tempo returned correlated traces for:

```text
model.gateway
tools/call diagnostic_echo
model.gateway
```

using the same run identifier.

An observability defect in the older deployed revision caused Model Gateway
Prometheus metrics to be absent.

The defect was already fixed in revision `9f23961`.

After roll-forward, Model Gateway metrics were successfully observed:

```text
agent_platform_model_requests_total{
  model="openrouter/free",
  provider="openrouter",
  status="succeeded"
} 2.0
```

and tool metrics remained functional.

This provided direct evidence that the roll-forward corrected observability
without changing agentic semantics.

### P7 — Failure recovery

**Result: PASS**

Both owned processes were terminated using SIGKILL.

No operator restart was performed.

Observed recovery:

| Service | Recovery time | Restart count |
|---|---:|---:|
| API | 3.573 s | 0 -> 1 |
| MCP | 4.078 s | 0 -> 1 |

Both returned to `active` and healthy automatically.

### P8 — Boot recovery

**Result: PASS**

The `agent01` workload guest was rebooted.

No application start or restart command was executed after boot.

Observed:

```text
boot_to_healthy_ms=6161
```

Post-boot state:

```text
API=active
MCP=active
API health=200
API metrics=200
MCP metrics=200
```

The active revision remained:

```text
9f239617fe608e995c29f0c29aa5bc985c556f46
```

A complete post-boot agentic smoke also passed:

```text
run_id: 6d8c7f2a-3d64-4a5e-a9d1-02dc72a3d0d7
output: Boot recovery succeeded.
```

A Proxmox warning regarding systemd 257 and optional nesting was observed during
the container reboot.

Nesting was not enabled because the workload booted successfully, systemd
restored the services correctly and no requirement gap was demonstrated.

### P9 — Roll-forward

**Result: PASS**

A new immutable release was prepared at:

```text
/opt/agent-platform/releases/9f23961
```

Preflight succeeded before activation:

```text
agent_platform import: OK
API import: OK
MCP import: OK
```

The active symlink was switched atomically:

```text
668b8c8 -> 9f23961
```

Both services restarted successfully and all health endpoints returned HTTP 200.

Post-roll-forward agentic smoke:

```text
run_id: 5184136b-1e2c-4309-80eb-f2d7ce118c0b
output: Roll forward succeeded.
```

Model metrics after roll-forward:

```text
agent_platform_model_requests_total{
  model="openrouter/free",
  provider="openrouter",
  status="succeeded"
} 2.0
```

Tool metrics after roll-forward:

```text
agent_platform_tool_requests_total{
  status="succeeded",
  tool="diagnostic_echo"
} 1.0
```

### P10 — Broken-release rollback

**Result: PASS**

A controlled broken release was created from the known-good release.

The failure mechanism removed only the candidate release's Python executable:

```text
/opt/agent-platform/releases/p10-broken/.venv/bin/python
```

The known-good release remained untouched.

After activation and restart, systemd observed:

```text
Result=exit-code
ExecMainStatus=203
ActiveState=activating
SubState=auto-restart
```

for both services.

Verification failed as expected:

```text
API health failed as expected
MCP verification failed as expected
```

Rollback atomically restored:

```text
/opt/agent-platform/releases/9f23961
```

Observed rollback recovery time:

```text
rollback_to_healthy_ms=1127
```

Post-rollback state:

```text
API=active
MCP=active
API health=200
API metrics=200
MCP metrics=200
```

A complete post-rollback semantic smoke passed:

```text
run_id: 5fba1870-f579-43ef-ac0b-db7316ea752e
output: Rollback succeeded.
```

## Success criteria

| Criterion | Result |
|---|---|
| SC1 — Automatic startup | PASS |
| SC2 — Automatic recovery | PASS |
| SC3 — Reproducible deployment | PASS |
| SC4 — Secret isolation | PASS |
| SC5 — Explicit networking | PASS |
| SC6 — Health | PASS |
| SC7 — Observability | PASS |
| SC8 — Version identity | PASS |
| SC9 — Rollback | PASS |
| SC10 — Semantic invariance | PASS |
| SC11 — Minimum sufficient complexity | PASS |

## Measurements

| Measurement | Result |
|---|---:|
| API process recovery | 3.573 s |
| MCP process recovery | 4.078 s |
| Guest boot to healthy | 6.161 s |
| Rollback to healthy | 1.127 s |
| `v0.1.1` release size | 110 MiB |
| `9f23961` release size | 111 MiB |
| Additional long-running control-plane processes | 0 |

Deployment duration, idle CPU usage and idle memory usage were not captured
during this experiment and are therefore not claimed.

## Guardrail status

No observed regression remained at the end of the experiment in:

- Model Gateway authentication;
- provider credential isolation;
- DSH Runtime Adapter behavior;
- model tool-call semantics;
- MCP capability execution;
- ToolRegistry behavior;
- metric separation by process;
- structured telemetry;
- OTLP trace export;
- `run_id` correlation.

No Docker, Compose, Kubernetes or K3s component was required.

Secrets were not committed to Git.

## Notable experiment findings

### OpenRouter credential drift

The first deployed runtime used an outdated OpenRouter credential and produced
HTTP 401 responses from the provider.

The credential was updated in the host-local environment file and the service was
restarted successfully.

This validated that provider credentials can be rotated independently of the
application release.

### Broken-release experiment iteration

The first P10 failure mechanism removed `.venv/bin/uvicorn`.

The systemd units actually execute:

```text
.venv/bin/python -m uvicorn
```

therefore that change did not break service startup.

The experiment was restored to the known-good release and the failure mechanism
was revised to remove only the candidate release's Python executable.

This produced the expected controlled `203/EXEC` startup failure.

The failed first attempt was useful evidence about the actual service execution
contract and did not modify the known-good release.

## Decision

**Accept C1 — systemd + Python virtual environment.**

The candidate satisfied all mandatory M5 success criteria and preserved the
platform's existing semantic behavior.

The architecture provides:

- persistent service lifecycle;
- automatic startup;
- automatic process recovery;
- explicit release identity;
- immutable versioned releases;
- atomic roll-forward;
- fast rollback;
- secret isolation;
- health verification;
- Prometheus metrics;
- OpenTelemetry traces;
- structured logs;
- real DSH -> model -> tool -> model semantic verification.

No additional orchestration or application control plane was required.

Under ADR-0002, adding Docker, Compose, Kubernetes, K3s or another deployment
technology would currently add complexity without evidence of a requirement gap
or measured benefit.

Such candidates remain admissible in the future only if new evidence justifies
their evaluation.

## Final recommendation

Promote C1 from experimental candidate to the current accepted deployment
architecture for Agent Platform homelab workloads.

Create a separate ADR recording this architectural decision.
