# M12.2 — Supervised Coding Application Use Case Decisions

- Status: Proposed for M12.2
- Date: 2026-09-18
- Related ADR: ADR-0010 — Supervised Coding Work V0
- Baseline main revision: `9b278bea9a88085454f60a97e10c76495da0d7b1`

## Goal

Connect the canonical M12.1 `CodingTask` to the existing coding Worker capability
without introducing verification or publication before their authority boundaries
exist.

The M12.2 path is intentionally:

```text
CodingTask
-> SupervisedCodingService
-> CodingChangeProducer
-> WorkerCodingChangeProducer
-> WorkerDevelopmentSession
-> ChangeSet
-> PreparedCodingTask
```

It stops there.

There is no trusted publication call in M12.2.

## Why `WorkerProposalRunner` is not used

The existing `WorkerProposalRunner` performs:

```text
WorkerDevelopmentSession
-> ChangeSet
-> publisher.publish(ChangeSet)
```

That behavior was valid for the M6 self-development experiment, but M12 requires
authoritative verification before publication.

Using `WorkerProposalRunner` here would create the wrong order:

```text
code
-> publish
-> verify later
```

M12 requires:

```text
code
-> ChangeSet
-> authoritative verification
-> trusted publication
```

Therefore M12.2 deliberately composes the existing
`WorkerDevelopmentSession` below a new application port instead of using the
publication-coupled proposal runner.

The existing M6 flow is not removed.

## Application boundary

`SupervisedCodingService` owns only the orchestration necessary at this stage.

It accepts a canonical:

```text
CodingTask
```

and invokes a:

```text
CodingChangeProducer
```

The producer returns an unverified:

```text
ChangeSet
```

The service verifies that:

```text
ChangeSet.base_revision == CodingTask.expected_base_revision
```

before returning the application result.

A mismatch fails closed and no later stage may consume the proposal.

## Application result

M12.2 introduces the smallest result that has a real producer:

```text
PreparedCodingTask
  task_id
  change_set
```

The name is intentionally not `CodingTaskResult`.

The result is not a completed coding task. It is only a prepared, unverified
proposal for the future verification stage.

There is no status enum because M12.2 has only two meaningful outcomes:

```text
return PreparedCodingTask
raise/fail
```

Verification and publication states have not earned fields yet.

## Worker adapter

`WorkerCodingChangeProducer` is the only M12.2 component that knows about
`WorkerDevelopmentTask`.

It maps:

```text
CodingTask.goal
-> WorkerDevelopmentTask.goal
```

and derives publication metadata from platform rules rather than request
authority:

```text
branch_name =
  coding/<task_id>

commit_message =
  chore: apply supervised coding task <task_id>
```

The caller still cannot choose:

```text
repository
base branch
publication branch
commit message
verification profile
```

## Expected-base semantics

`expected_base_revision` is a concurrency assertion.

M12.2 verifies it against the produced `ChangeSet`.

This check currently occurs after the Worker session has produced the ChangeSet.
That is sufficient to prevent a stale-base proposal from advancing, but it may
perform unnecessary coding work if the trusted base moved first.

An earlier pre-execution baseline check may be added when the execution/workspace
boundary is measured in M12.3 if evidence shows it is worth the additional
coupling.

M12.2 does not weaken the later trusted publisher remote-baseline invariant.

## Security boundary

M12.2 does **not** claim that the Worker is sandboxed.

It only establishes:

```text
canonical task != Worker-specific task
application service != Worker adapter
coding != verification
coding != publication
```

Filesystem, socket, network, credential, and resource confinement remain M12.3
and M12.4 acceptance work.

## No side effects beyond coding execution

The application service has no:

```text
TrustedPublicationClient
GitHub adapter
merge operation
verification implementation
```

dependency.

A successful M12.2 call means:

```text
"an unverified ChangeSet was prepared from the expected base"
```

It does not mean:

```text
"the change is acceptable"
"tests passed"
"the change was published"
"the change may be merged"
```

## M12.2 gate

Deterministic tests must prove:

```text
canonical CodingTask reaches a coding producer
task_id is preserved
Worker adapter receives the expected goal
branch metadata is derived deterministically
commit metadata is derived deterministically
expected-base mismatch fails closed
PreparedCodingTask contains the exact produced ChangeSet
no publisher is part of the application path
```

No network, GitHub write, real model invocation, verification, or trusted
publication belongs in this PR.

## Deferred

M12.2 deliberately does not implement:

```text
execution confinement
capability policy
authoritative verification
ChangeSet hashing
trusted publication integration
public API endpoint
trace correlation
Eval-as-Code suite
real coding smoke
```

Those remain assigned to later M12 sub-items.

> Complexity must earn its place.
