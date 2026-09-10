# M5 C1 Experiment Plan — systemd + Python virtual environment

- Status: Approved for experiment
- Date: 2026-09-10
- Baseline release: v0.1.0
- Baseline record: `docs/evidence/m5-deployment-baseline.md`
- Candidate evaluation: `docs/evidence/m5-deployment-candidate-evaluation.md`
- Governing ADR: ADR-0002 — Evidence-Gated Architecture

## Objective

Test whether the existing Agent Platform can be operated as a persistent homelab
workload using the smallest deployment architecture that appears capable of
satisfying M5 requirements:

- the existing Python application/runtime;
- a Python virtual environment;
- systemd for process lifecycle;
- a minimal versioned release layout;
- non-Git runtime configuration;
- explicit verification and rollback procedures.

This experiment does **not** pre-approve systemd as the final M5 architecture.

The candidate becomes Accepted only if the experiment satisfies all predefined
success criteria and guardrails.

## Hypothesis

### H1

A deployment based on systemd + the existing Python virtual-environment runtime,
combined with a small versioned release layout and deployment procedure, can
satisfy M5 requirements R1-R9 without introducing a container runtime,
Compose, K3s, Kubernetes, or another long-running control plane.

## Baseline

The observed V0 baseline currently has:

- two manually started Uvicorn processes;
- no Agent Platform systemd units;
- no Agent Platform containers;
- no declarative deployment artifacts;
- secrets loaded through the interactive development environment;
- loopback-only service binding;
- working health, metrics and tracing when processes are running;
- no declared rollout or rollback mechanism.

The baseline is the control for this experiment.

## Experimental environment

### Workload isolation

The experiment should run in an isolated workload guest rather than installing
Agent Platform application dependencies directly on the Proxmox management
host.

This does not introduce a new orchestration technology. It reuses the existing
homelab virtualization boundary and keeps the hypervisor host outside the
application dependency lifecycle.

A dedicated workload guest identifier, address and resource allocation must be
selected only after the Phase 0 inventory check.

### Initial operating-system assumption

Use the same minimal Debian-family guest pattern already used for lightweight
homelab workloads where practical.

The exact image/version must be recorded during provisioning.

## Proposed release layout

The experiment should test the following minimal layout:

```text
/opt/agent-platform/
├── releases/
│   ├── <release-a>/
│   │   ├── app/
│   │   ├── .venv/
│   │   └── REVISION
│   └── <release-b>/
│       ├── app/
│       ├── .venv/
│       └── REVISION
│
├── current -> releases/<active-release>/
│
└── shared/
    └── runtime.env
```

Principles:

- release directories are immutable after successful installation;
- `current` identifies the active release;
- rollback changes `current` back to the previous known-good release and
  restarts the services;
- runtime secrets/configuration remain outside release directories and Git;
- each release records the exact Git revision or release tag used.

The exact layout may be simplified if the experiment demonstrates that a
smaller arrangement satisfies the same requirements.

## Proposed process model

Two independent systemd units:

```text
agent-platform-api.service
agent-platform-mcp.service
```

Expected process ownership:

```text
systemd
├── agent-platform-api.service
│   └── <active-release>/.venv/bin/uvicorn
│       agent_platform.api.main:app
│
└── agent-platform-mcp.service
    └── <active-release>/.venv/bin/uvicorn
        agent_platform.api.mcp:app
```

A dedicated non-login workload user should own the application runtime where
practical.

The service definitions must not contain secret values.

## Secret-delivery experiment

Use a host-local runtime environment file outside the repository, for example:

```text
/etc/agent-platform/runtime.env
```

Requirements:

- not committed to Git;
- restrictive filesystem permissions;
- no interactive `source .env` requirement;
- loaded by the service manager;
- replaceable independently from application source.

The current application already consumes environment variables, so the
experiment should avoid adding a secret-management platform or changing the
application contract unless evidence demonstrates that the simple mechanism is
insufficient.

## Network experiment

The baseline binds both services to loopback.

The experiment must first identify actual consumers before widening exposure.

Expected consumers include:

- agent runtime / client for the Model Gateway;
- agent runtime / client for MCP;
- Prometheus for metrics;
- Tempo for outbound OTLP trace ingestion.

The deployment must expose only the minimum interfaces and ports necessary for
those consumers.

Binding to `0.0.0.0` is not considered the default solution.

Any LAN-facing binding must be explicit and documented.

## Dependency reproducibility observation

The current Python project declares a mixture of exact and ranged dependency
versions.

Therefore, installing the same release at different times may not necessarily
resolve an identical dependency set.

The experiment must record the installed dependency set for each tested release.

If reproducibility cannot be demonstrated with the current packaging metadata,
that becomes evidence for a dependency-locking or constraints mechanism.

No new dependency-management tool is pre-approved by this experiment.

## Release identity observation

The GitHub release is `v0.1.0`, while application package metadata may use a
different internal package version.

For M5, runtime identity must therefore be proven from an explicit deployed Git
revision/release record rather than inferred only from Python package metadata.

The experiment should create/read a `REVISION` artifact in each deployed release.

Alignment of package metadata may be handled separately if it becomes necessary.

## Experiment phases

### Phase 0 — Inventory and preflight

Goal: collect facts required to create the smallest isolated workload target.

Collect:

- existing Proxmox guests and VMIDs;
- current guest addresses;
- available Debian templates;
- storage availability;
- bridge/network information;
- host CPU/memory/storage headroom;
- reachability from monitoring and tracing components;
- an unused workload address;
- an unused VMID.

No infrastructure change occurs in this phase.

#### Gate P0

Proceed only when:

- an isolated target can be created without conflicting with existing guests;
- required network paths are understood;
- enough host resources are available for a small workload guest.

### Phase 1 — Provision experiment target

Goal: create only the minimum workload guest required for C1.

Record:

- guest identifier;
- hostname;
- OS/version;
- CPU;
- memory;
- storage;
- IP configuration;
- startup order if relevant.

Do not install Docker, Kubernetes, K3s, a database, or any additional control
plane.

#### Gate P1

The target must:

- boot successfully;
- have network connectivity;
- resolve/install required packages;
- reach the Tempo OTLP endpoint;
- be reachable from intended monitoring paths.

### Phase 2 — Install one known release

Goal: install a known Agent Platform release into a versioned release directory.

Record:

- Git release/tag;
- commit SHA;
- Python version;
- installed Python dependency set;
- installation duration;
- installed disk usage.

Create a release identity artifact:

```text
/opt/agent-platform/releases/<release>/REVISION
```

#### Gate P2

The installed release must be attributable to one exact repository revision.

### Phase 3 — Configure workload identity and secrets

Goal: remove interactive-shell dependency.

Create:

- dedicated workload account;
- host-local runtime environment file;
- minimum filesystem permissions.

Verify:

- secrets are absent from Git;
- services do not depend on an interactive shell;
- secret values are not printed by deployment verification.

#### Gate P3

Both services must be able to start with no manual `source .env`.

### Phase 4 — Add systemd lifecycle

Goal: test lifecycle requirements R1 and R2.

Create two versioned unit definitions or deployment-managed unit files:

```text
agent-platform-api.service
agent-platform-mcp.service
```

Required behaviors:

- start on boot;
- bounded restart on unexpected failure;
- predictable stop behavior;
- logs available through the host service manager;
- no shell session required to remain open.

#### Gate P4

Both services must reach `active (running)` and remain healthy after the
operator shell exits.

### Phase 5 — Functional verification

Goal: prove semantic invariance relative to v0.1.0.

Verify:

```text
Model Gateway /health   -> HTTP 200
Model Gateway /metrics  -> HTTP 200
MCP /metrics            -> HTTP 200
```

Then execute the real DSH agentic smoke path.

Expected semantic path:

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

#### Gate P5

The deployed candidate must preserve the validated v0.1.0 agentic behavior.

### Phase 6 — Observability verification

Goal: prove deployment has not degraded operational telemetry.

Verify:

- structured model lifecycle logs;
- structured tool lifecycle logs;
- Model Gateway Prometheus metrics;
- MCP/tool Prometheus metrics;
- OpenTelemetry export to Tempo;
- `tool.invoke` trace;
- same `run_id` usable for cross-process correlation.

#### Gate P6

The deployed workload must be observable to at least the same semantic level as
the v0.1.0 baseline.

### Phase 7 — Failure-recovery test

Goal: prove R2.

For each service independently:

1. confirm healthy state;
2. terminate the owned process unexpectedly;
3. observe systemd state;
4. measure recovery time;
5. verify health/metrics after recovery.

Record:

- failure timestamp;
- restart timestamp;
- time to healthy;
- number of restart attempts;
- final service state.

#### Gate P7

Each service returns automatically to healthy state without operator restart.

Restart policy must be bounded and must not create an uncontrolled crash loop.

### Phase 8 — Boot-recovery test

Goal: prove R1.

Procedure:

1. confirm healthy platform;
2. reboot only the isolated workload guest;
3. perform no interactive application startup;
4. measure time until both services are healthy;
5. run deployment verification;
6. run the agentic smoke.

#### Gate P8

The complete platform returns after guest boot without manual process startup.

### Phase 9 — Roll-forward test

Goal: prove versioned rollout.

Install a second test release or deliberately modified experimental revision as
a new release directory.

Switch `current` only after installation and preflight succeed.

Restart services and run full verification.

#### Gate P9

The active workload can be moved to a known new revision and the operator can
identify the active revision.

### Phase 10 — Broken-release rollback test

Goal: prove R9 using an intentional controlled failure.

Procedure:

1. preserve known-good release A;
2. prepare deliberately broken experimental release B;
3. activate B;
4. verify that deployment verification fails;
5. execute documented rollback;
6. restore `current` to A;
7. restart services;
8. repeat health, observability and agentic smoke verification.

The failure must be safe and reversible. Do not corrupt persistent data or
credentials to simulate the failure.

#### Gate P10

Rollback restores the previous known-good revision and all mandatory health and
agentic checks pass.

## Success criteria

C1 is accepted only if all of the following are demonstrated.

### SC1 — Automatic startup

Both services return automatically after guest boot.

### SC2 — Automatic recovery

Both services recover from unexpected process termination without manual
restart.

### SC3 — Reproducible deployment

A documented compatible host can be brought to a known Agent Platform revision
using versioned deployment artifacts and commands.

### SC4 — Secret isolation

Runtime credentials remain outside Git and no interactive shell sourcing is
required.

### SC5 — Explicit networking

Only required service interfaces/ports are exposed.

### SC6 — Health

Required API/MCP health and metrics checks pass after deployment and recovery.

### SC7 — Observability

Logs, metrics, Tempo traces and `run_id` correlation remain functional.

### SC8 — Version identity

The operator can determine the exact active release/revision.

### SC9 — Rollback

A deliberately broken rollout can be restored to the previous known-good
release using the documented procedure.

### SC10 — Semantic invariance

The real DSH model -> tool -> model smoke continues to succeed.

### SC11 — Minimum sufficient complexity

No additional runtime/control plane is required to achieve SC1-SC10.

## Measurements

Record at least:

| Measurement | Baseline | Candidate |
|---|---:|---:|
| Manual commands required after boot | TBD/observed manual | |
| Time from guest boot to healthy | N/A | |
| API process recovery time | N/A | |
| MCP process recovery time | N/A | |
| Deployment duration | Manual / not defined | |
| Rollback duration | Not defined | |
| Release disk usage | N/A | |
| Idle memory usage | TBD | |
| Idle CPU usage | TBD | |
| Additional long-running control-plane processes | 0 | |

Measurements are used to describe operational cost, not to manufacture a score
when a requirement is already clearly satisfied.

## Guardrails

The experiment must not regress:

- Model Gateway authentication;
- provider credential isolation;
- DSH Runtime Adapter behavior;
- model tool-call semantics;
- MCP capability execution;
- ToolRegistry behavior;
- metric separation by process;
- structured telemetry;
- OTLP trace export;
- `run_id` correlation;
- existing CI tests.

The experiment must not:

- commit secrets;
- log tool arguments or outputs by default;
- install application dependencies directly on the Proxmox management host;
- introduce Docker, Compose, Kubernetes or K3s without new evidence;
- convert experimental infrastructure into production state before the
  experiment decision is recorded.

## Decision rule

### Accept C1

Accept systemd + Python virtual environment for M5 if all mandatory success
criteria pass and no guardrail is violated.

### Defer C1

Defer if the experiment is incomplete or evidence is ambiguous.

### Reject C1

Reject only if a mandatory M5 requirement cannot be satisfied adequately
without adding complexity that eliminates C1's simplicity advantage.

If C1 is rejected, the failure itself becomes the evidence used to evaluate C2.

C2 or C3 must not be introduced simply because they are more feature-rich.

## Required experiment evidence

At completion, create:

```text
docs/evidence/m5-systemd-experiment-results.md
```

The results record must contain:

- environment;
- exact release/revisions;
- executed tests;
- measured results;
- failures;
- guardrail status;
- final Accepted / Rejected / Deferred recommendation.

If C1 is Accepted, create a separate ADR for the deployment architecture.

The experiment plan itself does not constitute architectural acceptance.

## Next action

Execute Phase 0 only.

Do not provision or modify infrastructure until the Phase 0 inventory and
network/resource evidence have been reviewed.
