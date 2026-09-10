# ADR-0002: Evidence-Gated Architecture — Complexity Must Earn Its Place

- Status: Accepted
- Date: 2026-09-10

## Context

The Agent Platform has completed its first functional vertical slice and now has
multiple plausible directions for expansion: new runtimes, model providers,
routing policies, capability brokers, retrieval mechanisms, observability
components, persistence layers, control-plane services and deployment
technologies.

At this stage, the main architectural risk is no longer proving that the
platform can work. The risk is allowing complexity to enter faster than the
platform demonstrates a need for it.

A technology, abstraction or architectural pattern must not be adopted only
because it is elegant, popular, fashionable, widely used, described as a best
practice, or potentially useful in the future.

The current system is the baseline. Complexity must justify displacing that
baseline.

## Decision

The Agent Platform adopts **Evidence-Gated Architecture** as a binding
architectural principle:

> **Nothing new enters the architecture without evidence. Complexity must earn
> its place.**

No new abstraction, component, service, protocol, framework, database, agent,
runtime, model, provider, tool, retrieval mechanism, observability component,
control-plane layer, deployment technology, persistence mechanism, or other
material architectural change may be introduced unless at least one of the
following conditions is satisfied.

### 1. Requirement gap

There is a clear functional, operational, reliability, security, compliance,
performance, cost, or maintainability requirement that the current stack cannot
satisfy adequately.

The evidence must identify:

- the requirement;
- the current behavior or limitation;
- the concrete impact of that limitation;
- the acceptance criteria;
- why the existing stack cannot satisfy the requirement with a smaller change.

A requirement gap is evidence. It does not require an artificial benchmark if
the unmet need can already be demonstrated directly.

### 2. Measured improvement

For a non-essential improvement, optimization, replacement, refactor, or
architectural enhancement, a reproducible experiment demonstrates a concrete
benefit over the current baseline.

Before implementation, the proposal must define:

- hypothesis;
- baseline;
- success metric;
- guardrails;
- comparative experiment;
- decision rule.

The candidate is accepted only if the measured result satisfies the predefined
success criteria without violating the guardrails.

If the expected gain is not demonstrated, the change does not enter the
architecture.

An inconclusive experiment results in **Deferred**, not Accepted.

## Default decision

The default architectural decision is:

> **Keep the current system and prefer the minimum sufficient solution.**

The burden of proof belongs to the proposed complexity, not to the existing
baseline.

Future flexibility by itself is not sufficient evidence.

“Best practice” by itself is not sufficient evidence.

Technology preference by itself is not sufficient evidence.

Popularity, novelty, elegance, vendor recommendation, benchmark marketing, or
industry trend by themselves are not sufficient evidence.

## Required ADR content

Any ADR proposing a material architectural addition or replacement must contain
enough information to evaluate the evidence gate.

At minimum:

1. **Trigger** — what concrete problem, requirement, risk or hypothesis caused
   the proposal.
2. **Current baseline** — how the existing system behaves today.
3. **Gap or hypothesis** — what the current architecture cannot do, or what
   improvement is expected.
4. **Alternatives** — including the explicit alternative of making no
   architectural change.
5. **Evidence** — measurements, incidents, requirements, experiments, traces,
   tests, operational data, cost data, or other reproducible evidence.
6. **Success criteria** — what must be true for the change to be accepted.
7. **Guardrails** — what must not regress.
8. **Decision** — Accepted, Rejected, or Deferred.
9. **Consequences** — new complexity, operational cost, failure modes and
   removal/rollback considerations.

Implementation must not begin before the evidence required to make the
architectural decision is available, except for a deliberately scoped
experiment whose purpose is to generate that evidence.

## Experiments are not production architecture

A prototype, benchmark, spike or experiment may temporarily introduce a
candidate technology for evaluation.

That experiment does not make the technology part of the platform.

Experimental code must remain isolated from the production architecture until
the ADR is Accepted.

The experiment should be the smallest implementation capable of testing the
hypothesis.

## Semantic invariance

When a proposed refactor claims to preserve behavior, the evidence should test
that claim.

The current implementation is the semantic baseline. The candidate should be
compared against it using relevant tests, traces, outputs, protocol behavior,
latency, error behavior, resource usage or other observable properties.

If the refactor is intended to be behavior-preserving, unexplained semantic
differences are regressions unless the ADR explicitly accepts them.

Semantic-invariance analysis is therefore one valid form of architectural
evidence.

## Emergency and security changes

An incident, confirmed vulnerability, compliance obligation, or immediate
operational risk may itself constitute a requirement gap.

Emergency mitigation may be implemented before the ADR is completed when delay
would increase material risk.

The architectural decision and evidence must still be documented as soon as it
is operationally safe to do so.

Emergency handling is not an exemption from the evidence requirement.

## Enforcement

Architecture-affecting pull requests must reference an Accepted ADR or clearly
state that they do not introduce a new architectural element.

A proposal that has not passed the evidence gate remains in the roadmap,
cemetery of ideas, or experiment backlog. It does not enter the implementation
backlog.

Automation of this policy through CI, bots, policy engines, or an Architecture
Evidence system is itself subject to this ADR. The process remains
documentation-first until evidence shows that manual enforcement is
insufficient.

## Application to the current roadmap

This ADR changes how the post-v0.1.0 roadmap is executed.

### Model routing and provider registry

A Model Registry, routing policy, provider fallback, retry orchestration,
budgets, or cost controls are not introduced merely because they would make the
Model Gateway more extensible.

They become admissible when a concrete requirement appears, such as:

- more than one provider/model must be selected dynamically;
- provider failure requires automated failover;
- measurable cost or latency optimization requires routing;
- policy or workload constraints require model selection.

Until then, the existing single-provider path remains the baseline.

### Capability Broker and capability resolution

A Capability Broker, resolver, BM25/FTS5 index, top-k tool selection, hybrid
retrieval, embeddings, or LLM reranking are not introduced while the current
tool catalogue can be exposed and operated adequately.

They become admissible when evidence shows a concrete problem such as:

- tool catalogue size causes context, latency, quality, or cost degradation;
- runtime/tool coupling prevents a required integration;
- measurable tool-selection errors require a resolver;
- capability policy or discovery requirements cannot be met by the existing
  registry.

The simplest resolver capable of satisfying the demonstrated need must be
preferred.

### M5 deployment

Declarative deployment and operational lifecycle work is already admissible
under this ADR because the current V0 requires manual process startup and does
not yet provide persistent service lifecycle, restart/recovery, declarative
deployment, or production-style operations.

Those are documented limitations of the current baseline and therefore
constitute a clear operational requirement gap.

The specific implementation technology for M5 is not pre-approved. Compose,
systemd, containers, K3s, Kubernetes, Nomad, or any other candidate must still
earn its place against the actual deployment requirements.

## Consequences

### Positive

- Reduces speculative architecture and premature abstraction.
- Keeps the platform understandable and replaceable.
- Forces architectural decisions to be falsifiable.
- Creates a historical record of why complexity was accepted.
- Makes rejected experiments useful rather than wasted work.
- Encourages measurement before migration.
- Aligns architecture with demonstrated system needs.

### Negative

- Some changes will take longer to approve because evidence must be collected.
- Experiments may be required before implementation.
- Attractive technologies may remain intentionally unused.
- The platform may temporarily retain an imperfect implementation when the
  evidence does not justify replacing it.

These costs are accepted because unnecessary architectural complexity has a
longer operational lifetime than the experiment required to avoid it.

## Result

From this ADR forward, architectural evolution follows:

```text
Need or hypothesis
        |
        v
Current baseline
        |
        v
Evidence plan
        |
        +---- clear unmet requirement
        |              |
        |              v
        |         ADR decision
        |
        +---- measured improvement
                       |
                       v
                   experiment
                       |
                       v
                compare to baseline
                       |
              +--------+--------+
              |                 |
           proven            not proven
              |                 |
              v                 v
          Accepted       Rejected/Deferred
              |
              v
        implementation
```

Architecture is no longer expanded because a technology appears useful.

It is expanded because the current system has demonstrated that the complexity
is necessary or because evidence has demonstrated that the change is better.
