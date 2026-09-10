# M5 Deployment Candidate Evaluation

- Status: Proposed
- Date: 2026-09-10
- Baseline: `docs/evidence/m5-deployment-baseline.md`
- Governing ADR: ADR-0002 — Evidence-Gated Architecture

## Objective

Compare deployment mechanisms against the requirements derived from the
observed V0 baseline.

This document does not approve a deployment technology by reputation,
popularity, or expected future usefulness.

The preferred candidate is the minimum solution that can satisfy all mandatory
requirements with the lowest additional operational complexity.

## Requirements

### Mandatory

- **R1** — Automatic startup after host boot.
- **R2** — Automatic bounded restart after process failure.
- **R3** — Declarative and reproducible deployment.
- **R4** — Secure, non-Git, non-interactive secret delivery.
- **R5** — Explicit and minimal network exposure.
- **R6** — Post-deployment health verification.
- **R7** — Continuity of logs, Prometheus metrics, OpenTelemetry traces and
  `run_id` correlation.
- **R8** — Running workload attributable to a known release/revision.
- **R9** — Documented and tested rollback.
- **R10** — Minimum sufficient complexity.

### Current non-requirements

The baseline does not currently demonstrate a need for:

- multi-node scheduling;
- high availability;
- autoscaling;
- service mesh;
- cluster-level orchestration;
- workload bin-packing;
- Kubernetes APIs;
- containerization itself.

A candidate receives no benefit for providing capabilities that are not
required.

## Candidates

### C0 — Current manual process model

Keep the current developer-shell workflow:

- source virtual environment;
- source `.env`;
- start two Uvicorn processes manually.

This is retained as the explicit "no architectural change" baseline.

### C1 — systemd + Python virtual environment

Run the two existing Python services directly under systemd.

Possible deployment shape:

```text
/opt/agent-platform/
├── releases/
│   ├── <release-a>/
│   └── <release-b>/
├── current -> releases/<active-release>/
└── shared/
    └── runtime configuration / secrets

systemd
├── agent-platform-api.service
└── agent-platform-mcp.service
```

The services continue using the existing application/runtime model.

### C2 — Containers + Compose with host service ownership

Package the API and MCP processes as container images and define them through
Compose.

A host service manager may own the Compose application lifecycle.

This introduces:

- image build and image lifecycle;
- container runtime;
- Compose manifests;
- container networking;
- container-specific deployment and rollback behavior.

### C3 — K3s

Deploy the platform as Kubernetes workloads on K3s.

This introduces:

- Kubernetes control plane;
- Kubernetes manifests/resources;
- scheduler;
- service discovery;
- workload controller semantics;
- cluster networking;
- additional operational state and failure modes.

## Paper evaluation

Legend:

- **Yes** — capability can satisfy the requirement directly with normal
  configuration.
- **Partial** — additional deployment logic or conventions are required.
- **No** — candidate does not satisfy the requirement in its current form.
- **Excess** — candidate supplies materially more machinery than the observed
  requirement needs.

| Requirement | C0 Manual | C1 systemd + venv | C2 Containers + Compose | C3 K3s |
|---|---|---|---|---|
| R1 Automatic startup | No | Yes | Yes | Yes |
| R2 Process recovery | No | Yes | Yes | Yes |
| R3 Declarative deployment | No | Partial | Yes | Yes |
| R4 Secure secret delivery | No | Yes | Yes | Yes |
| R5 Explicit network exposure | Partial | Yes | Yes | Yes |
| R6 Health verification | Manual | Partial | Partial | Partial |
| R7 Observability continuity | Yes while running | Yes | Yes | Yes |
| R8 Versioned rollout | No | Partial | Yes | Yes |
| R9 Tested rollback | No | Partial | Partial | Partial |
| R10 Minimum complexity | Yes, but insufficient | Strong | Moderate | Weak |
| Unrequired orchestration overhead | None | None | Some | High |
| New runtime layer | None | None | Container runtime | Container runtime + Kubernetes |

## Interpretation

### C0 — Rejected for M5

The current process model fails multiple demonstrated requirements.

No further experiment is required to reject it as the M5 deployment solution.

### C3 — K3s is not currently justified

K3s can satisfy the lifecycle requirements, but the observed baseline does not
require the capabilities that justify introducing a cluster control plane.

There is currently no demonstrated requirement for:

- scheduling across nodes;
- Kubernetes reconciliation APIs;
- service mesh;
- autoscaling;
- high availability;
- Kubernetes-native ecosystem integration.

Under ADR-0002, those capabilities do not count as benefits unless they solve a
demonstrated requirement.

K3s therefore remains deferred unless a later requirement or experiment shows
a concrete advantage that offsets its additional control-plane complexity.

### C2 — viable, but containerization must earn its place

Containers and Compose can satisfy the M5 requirements.

However, the baseline does not currently demonstrate a portability,
dependency-isolation, image-distribution, multi-service packaging, or immutable
artifact problem that requires containerization.

Containerization therefore remains a viable candidate, but it does not yet
have enough evidence to displace a simpler direct-process deployment.

### C1 — leading minimal candidate

systemd directly addresses the demonstrated lifecycle gaps:

- automatic startup;
- process supervision;
- restart policy;
- dependency ordering;
- runtime identity;
- environment/credential injection;
- logging through the host service manager.

It does not by itself fully solve reproducible rollout and rollback.

Those gaps can potentially be satisfied with a small release layout and
versioned deployment/verification script without introducing a second runtime
layer.

For that reason, C1 is the leading candidate for an experiment.

This is not yet an architectural acceptance.

## Experiment hypothesis

### H1

A deployment using systemd + the existing Python virtual-environment runtime,
combined with a minimal versioned release layout and deployment script, can
satisfy R1-R9 without introducing a container runtime or cluster control plane.

## Experimental scope

The experiment must be the smallest implementation able to test H1.

It should prove:

1. installation of a known Agent Platform release;
2. deterministic dependency installation;
3. two systemd-managed services;
4. automatic startup;
5. bounded automatic restart;
6. non-interactive secret delivery outside Git;
7. explicit network binding;
8. API and MCP post-deploy verification;
9. Prometheus/Tempo continuity;
10. rollback to a previous known-good release.

The experiment should not add:

- Docker;
- Compose;
- Kubernetes/K3s;
- a deployment controller;
- a secret-management platform;
- a service mesh;
- additional databases.

Those components require independent evidence.

## Proposed success criteria

C1 is accepted for M5 only if the experiment demonstrates all of the following.

### SC1 — Boot recovery

After a workload-host reboot, both required services return without interactive
operator action.

### SC2 — Process recovery

When either service process is terminated unexpectedly, the service manager
returns it to a healthy state automatically.

Restart behavior must be bounded to avoid uncontrolled crash loops.

### SC3 — Reproducibility

A clean compatible host can be brought from documented prerequisites to a
running known release using versioned repository artifacts and documented
commands.

### SC4 — Secret isolation

Runtime secrets are absent from Git and are not required in an interactive
developer shell.

The deployment runs under a dedicated workload identity where practical.

### SC5 — Health

After deployment:

```text
Model Gateway /health   -> HTTP 200
Model Gateway /metrics  -> HTTP 200
MCP /metrics            -> HTTP 200
```

The agentic smoke test must also pass.

### SC6 — Observability continuity

The deployed workload must continue producing:

- structured lifecycle logs;
- model and tool Prometheus metrics;
- OpenTelemetry traces in Tempo;
- cross-process `run_id` correlation.

### SC7 — Version identity

The operator can determine which Agent Platform release/revision is currently
active.

### SC8 — Rollback

A deliberately broken deployment can be reverted to the previous known-good
release using the documented rollback procedure.

The rollback must restore the health checks and agentic smoke test.

### SC9 — Operational simplicity

The solution must not introduce an additional long-running control plane or
runtime layer beyond what is necessary to satisfy the requirements.

## Guardrails

The experiment must not regress:

- the validated model -> tool -> model loop;
- Model Gateway authentication;
- OpenRouter credential isolation;
- MCP tool execution;
- Prometheus metric separation by process;
- OpenTelemetry export to Tempo;
- `run_id` correlation;
- the existing CI test suite.

Secrets and tool arguments/outputs must not be added to telemetry.

## Decision rule

- If C1 satisfies SC1-SC9, accept C1 as the M5 deployment architecture.
- If C1 fails a mandatory criterion because of a fundamental limitation,
  evaluate C2 against that specific demonstrated gap.
- Evaluate C3 only if C1/C2 cannot satisfy a demonstrated requirement or an
  experiment shows a concrete measurable benefit that justifies K3s complexity.
- Do not introduce additional infrastructure solely to prepare for hypothetical
  future scale.

## Current decision

- C0 — **Rejected**
- C1 — **Experiment approved**
- C2 — **Deferred**
- C3 — **Deferred**

No deployment architecture is Accepted yet.

The next action is to design and execute the C1 experiment.
