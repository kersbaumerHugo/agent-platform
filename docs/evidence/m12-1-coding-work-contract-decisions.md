# M12.1 — Coding Work Contract Decisions

- Status: Proposed for M12.1
- Date: 2026-09-18
- Related ADR: ADR-0010 — Supervised Coding Work V0

## Goal

Define the smallest platform-owned contract for one supervised coding request
without leaking Worker-, runtime-, repository-publication-, or verification-specific
authority into the request.

## Accepted V0 request shape

```text
CodingTask
  task_id
  goal
  expected_base_revision
```

### `task_id`

Earned its place because every later execution, verification, publication, and
trace needs one stable task identity.

The caller may supply it for deterministic testing; otherwise the domain model
generates a UUID.

### `goal`

Earned its place because it is the human-owned coding intent.

Whitespace-only values fail validation and surrounding whitespace is normalized.

### `expected_base_revision`

Earned its place because the supervised task must be bound to an exact repository
baseline before execution.

For the current repository topology it is represented as a full Git SHA-1.

The value is a concurrency assertion only. It is **not** a branch selector and
does not grant authority to redirect the trusted publication target.

## Fields that did not earn their place

The request intentionally does not accept:

```text
repository_url
base_branch
branch_name
commit_message
verification_profile
contexts
```

### Repository and base branch

The target repository and trusted base branch remain platform composition /
trusted configuration in V0.

A coding request must not redirect publication to an arbitrary repository or
branch.

### Branch name

The publication branch will be derived under platform/trusted publication rules
when publication is integrated.

It is not caller authority.

### Commit message

The commit message is publication metadata, not core coding intent.

It will be derived or constrained later where it has a real consumer.

### Verification profile

Authoritative verification is platform-owned by ADR-0010.

Allowing the coding request to select a weaker profile would collapse the
verification authority boundary.

### Context references

M11 context composition remains available to the platform, but M12.1 has no live
coding-context consumer yet.

Context references are therefore deferred rather than added speculatively.

## Contract hardening

`CodingTask` is:

```text
extra = forbid
frozen = true
```

This ensures unknown authority-bearing fields fail closed and the validated task
cannot be mutated in place.

The JSON schema is intentionally limited to exactly:

```text
task_id
goal
expected_base_revision
```

## Result contract decision

A first-class `CodingTaskResult` does **not** earn its place in M12.1.

There is not yet an application lifecycle capable of producing a stable outcome.
Inventing result fields now would force semantics for:

```text
execution
ChangeSet
verification
publication
PR state
```

before those consumers exist.

M12.2 is the first point where an application result has a real producer. The
result contract should be introduced there from observed needs rather than
predeclared in M12.1.

This is an intentional evidence-gated deviation from the experiment-plan
candidate wording "request and result": the request is promoted now; the result
is deferred until a live application boundary exists.

## M12.1 gate

The unit contract suite must prove:

```text
blank goal rejected
goal normalization deterministic
invalid/non-full base revision rejected
base revision canonicalized
unknown authority fields rejected
schema contains only V0 fields
serialization deterministic
validated task immutable
Worker-specific types absent from the canonical contract
```

No Worker, verifier, publisher, GitHub, or network side effect belongs in M12.1.
