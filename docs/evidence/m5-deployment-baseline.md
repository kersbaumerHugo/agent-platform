# M5 Deployment Baseline & Evidence Record

- Status: Observed
- Date: 2026-09-10
- Baseline release: v0.1.0
- Governing ADR: ADR-0002 — Evidence-Gated Architecture

## Objective

Establish the operational baseline of Agent Platform before selecting or introducing a deployment technology.

This document records observed facts first and derives requirements from those facts.

No deployment technology is selected by this record.

## Observed baseline

### Runtime environment

The Agent Platform currently runs on a developer workstation.

Observed runtime:

```text
hostname: localhost-live
Python: 3.14.7
```

### Process lifecycle

Two independent Uvicorn processes are started manually from the project virtual environment:

```text
agent_platform.api.main:app
  bind: 127.0.0.1:8000

agent_platform.api.mcp:app
  bind: 127.0.0.1:8001
```

No Agent Platform systemd unit was present.

No Agent Platform container was observed.

Therefore the current execution model depends on interactive/manual process startup.

### Network exposure

Both services currently listen only on loopback:

```text
127.0.0.1:8000
127.0.0.1:8001
```

This is adequate for the current local validation flow but does not provide remote service reachability.

Any future deployment must expose only the interfaces required by its actual consumers.

### Health and observability endpoints

Observed:

```text
Model Gateway /health   -> HTTP 200
Model Gateway /metrics  -> HTTP 200
MCP /metrics            -> HTTP 200
```

The V0 already exports OpenTelemetry traces to the homelab Tempo backend.

### Secret delivery

The following credentials were observed as present in the execution environment:

```text
OPENROUTER_API_KEY
MODEL_GATEWAY_API_KEY
```

The current local workflow loads configuration through the interactive shell and `.env`.

Credentials are not intended to be committed to Git.

### Deployment artifacts

No deployment artifact matching the following was found in the repository baseline:

```text
Dockerfile
compose.yml
docker-compose.yml
*.service
*.container
*.k8s.yml
*.k8s.yaml
```

The repository therefore does not currently define how the Agent Platform is installed, started, recovered or rolled back as a persistent workload.

## Demonstrated requirement gaps

### G1 — Persistent lifecycle

The platform depends on manually started foreground processes.

There is no declared mechanism for automatic startup after host boot.

### G2 — Failure recovery

No service manager or workload supervisor currently owns the API or MCP processes.

There is no declared automatic restart behavior after process failure.

### G3 — Reproducible deployment

The repository contains application code but no persistent deployment definition.

Recreating the running platform therefore depends on undocumented/manual operator actions.

### G4 — Secret delivery

Secrets are currently injected through the interactive development environment.

A persistent deployment requires non-Git secret delivery that does not depend on manually sourcing a developer `.env`.

### G5 — Network reachability

The V0 services bind only to loopback.

A homelab deployment requires an explicit network exposure model for the components that must be reached by other hosts.

Exposure must remain minimal rather than defaulting to unrestricted LAN access.

### G6 — Deployment verification

The platform exposes useful health and observability endpoints, but there is no deployment procedure that verifies them after rollout.

### G7 — Rollback

There is no declared procedure for returning from a failed deployment to a previous known-good Agent Platform release.

## Derived M5 requirements

### R1 — Automatic startup

Required services must return automatically after the workload host boots.

### R2 — Automatic process recovery

Unexpected process termination must trigger bounded automatic restart.

Restart behavior must avoid uncontrolled crash loops.

### R3 — Declarative deployment

The repository must contain enough versioned deployment configuration to reproduce the service from a known host baseline.

### R4 — Secure secret delivery

Runtime credentials must:

- remain outside Git;
- not require interactive shell setup;
- be readable only by the workload identity where practical;
- be replaceable without modifying application source code.

### R5 — Explicit network exposure

The deployment must declare which interfaces and ports are reachable.

Only required consumers should receive access.

### R6 — Health verification

Deployment verification must confirm at minimum:

- Model Gateway health;
- Model Gateway metrics;
- MCP service availability;
- MCP metrics.

### R7 — Observability continuity

The deployed platform must continue to provide:

- structured logs;
- Prometheus metrics;
- OpenTelemetry trace export;
- run_id correlation.

### R8 — Versioned rollout

The deployed workload must be attributable to a known repository revision or release.

### R9 — Tested rollback

A deployment must have a documented and tested path back to the previous known-good version.

### R10 — Minimal sufficient complexity

The selected deployment architecture must be the minimum solution that satisfies R1-R9.

A scheduler, cluster orchestrator or additional control plane is not justified unless a requirement or comparative experiment demonstrates its necessity.

## Non-requirements

The current evidence does not demonstrate a need for:

- Kubernetes;
- K3s;
- multi-node scheduling;
- high availability;
- service mesh;
- autoscaling;
- distributed orchestration;
- containerization itself.

These remain candidate mechanisms or future ideas, not M5 requirements.

## Next evidence step

Evaluate candidate deployment mechanisms against R1-R10.

At minimum compare:

1. systemd + Python virtual environment;
2. containerized services with Compose/systemd ownership;
3. K3s.

The comparison must include the explicit baseline option of making the smallest possible change.

The selected technology must satisfy all mandatory requirements while adding the least operational complexity.
