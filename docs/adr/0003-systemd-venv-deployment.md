# ADR-0003: Use systemd and Python virtual environments for current deployment

- Status: Accepted
- Date: 2026-09-14

## Trigger

The Agent Platform V0 could execute its validated runtime path but required
manual process startup and lacked persistent lifecycle management, automatic
recovery, versioned rollout and tested rollback.

M5 therefore required a deployment architecture.

ADR-0002 requires deployment complexity to be justified by evidence rather than
introduced by convention or preference.

## Current baseline

Before M5, the platform used manually started Uvicorn processes from a
development environment.

The baseline did not provide:

- automatic startup after guest boot;
- automatic process recovery;
- versioned release activation;
- explicit deployed revision identity;
- tested rollback;
- service-manager-owned logs;
- host-managed runtime secret loading.

## Hypothesis

A minimal deployment using:

- an isolated homelab workload guest;
- systemd;
- a Python virtual environment;
- immutable versioned release directories;
- an atomic `current` symlink;
- host-local environment files;

can satisfy the M5 operational requirements without introducing Docker,
Compose, Kubernetes, K3s or another application control plane.

## Alternatives

### Keep manual process startup

Rejected.

It does not satisfy persistent lifecycle, automatic recovery, boot recovery or
operational deployment requirements.

### systemd + Python virtual environment

Accepted.

It is the smallest candidate that satisfied all required criteria in the M5
experiment.

### Docker or Docker Compose

Deferred.

No demonstrated requirement currently requires an additional container runtime
for the Agent Platform workload.

### K3s or Kubernetes

Deferred.

No demonstrated scheduling, scaling, orchestration or cluster requirement
currently justifies this complexity.

These alternatives may be evaluated later if new evidence demonstrates a
requirement gap or measurable benefit.

## Evidence

The full experiment is recorded in:

```text
docs/evidence/m5-systemd-experiment-results.md
```

Observed results include:

- API automatic recovery: 3.573 s;
- MCP automatic recovery: 4.078 s;
- workload guest boot to healthy: 6.161 s;
- controlled rollback to healthy: 1.127 s;
- successful immutable roll-forward from `668b8c8` to `9f23961`;
- successful controlled broken-release detection;
- successful post-rollback agentic execution;
- Prometheus model and tool metrics;
- OpenTelemetry traces with `run_id` correlation;
- successful DSH -> Model Gateway -> OpenRouter -> MCP -> ToolRegistry ->
  DiagnosticEchoTool -> model execution.

All M5 experiment gates P0-P10 passed.

All success criteria SC1-SC11 passed.

## Decision

The Agent Platform accepts **systemd + Python virtual environment** as the
current deployment architecture for the homelab workload.

The accepted runtime deployment pattern is:

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
└── current -> releases/<active-release>
```

Runtime configuration and secrets remain outside Git under the host-local
configuration boundary.

Two independent systemd services own the runtime lifecycle:

```text
agent-platform-api.service
agent-platform-mcp.service
```

Roll-forward installs and verifies a new immutable release before atomically
switching `current`.

Rollback repoints `current` to the previous known-good release and restarts the
services.

## Success criteria

The decision is considered valid while this architecture continues to satisfy:

- automatic startup;
- automatic failure recovery;
- explicit deployed revision identity;
- health verification;
- observability;
- secret isolation;
- semantic invariance;
- reproducible release installation;
- safe roll-forward;
- safe rollback.

## Guardrails

The deployment architecture must not:

- place runtime secrets in Git;
- install application dependencies directly on the Proxmox host;
- remove version identity from deployed releases;
- bypass the Model Gateway credential boundary;
- regress model or tool observability;
- regress `run_id` correlation;
- mutate known-good release directories during rollout or rollback.

Release directories are treated as immutable after successful installation.

## Consequences

### Positive

- No additional application control plane is required.
- Lifecycle management uses the operating system's existing service manager.
- Failure recovery is automatic.
- Boot recovery is automatic.
- Releases are attributable to exact Git revisions.
- Roll-forward and rollback are explicit and fast.
- Secrets can be rotated independently of application source.
- The architecture is simple enough to inspect and troubleshoot directly.

### Negative

- Deployment is currently host-oriented rather than cluster-oriented.
- Release preparation remains an operator-driven procedure.
- Dependency resolution is not fully locked by the current project metadata.
- Horizontal scheduling, autoscaling and multi-node placement are not provided.
- systemd unit and host configuration management remain deployment concerns.

These are accepted limitations because none currently represents an unmet M5
requirement.

## Re-evaluation triggers

This ADR should be revisited if evidence demonstrates one or more of the
following:

- multiple workload nodes require coordinated scheduling;
- rolling deployment without service interruption becomes a requirement;
- horizontal scaling becomes necessary;
- workload placement or resource scheduling becomes necessary;
- container-level packaging materially improves reproducibility;
- dependency isolation becomes insufficient;
- host configuration drift becomes operationally significant;
- a Docker, K3s, Kubernetes or other candidate demonstrates measurable benefit
  against the current baseline.

Until such evidence exists, systemd + Python virtual environments remain the
minimum sufficient deployment solution.

## Rollback of this architectural decision

This ADR does not make systemd permanent.

If a future candidate satisfies an evidence-gated replacement experiment, the
platform may adopt a different deployment backend.

The deployment architecture must remain subordinate to platform requirements,
not become part of the Agent Platform domain model.
