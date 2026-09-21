# M12.6 — Verified ChangeSet Publication Integrity

Status: Accepted for M12 V0 evidence

## Decision

M12.6 accepts the supervised coding publication path only when the exact `ChangeSet`
that passed authoritative verification is the same semantic `ChangeSet` submitted to
the trusted publication authority.

The accepted flow is:

```text
CodingTask
  -> SupervisedCodingService
  -> PreparedCodingTask
  -> canonical ChangeSet identity
  -> disposable verification workspace at exact trusted base
  -> authoritative verification in hardened Docker boundary
  -> post-verification exact ChangeSet revalidation
  -> VerifiedChangeSet
  -> VerifiedChangePublisher
  -> TrustedPublisher
  -> publication sink
```

## Core invariant

```text
trusted base
  -> exact ChangeSet
  -> authoritative verification
  -> SAME ChangeSet
  -> trusted publication
```

Verification evidence is not enough by itself. The platform also revalidates the
materialized workspace after verification and binds successful evidence to a stable
`ChangeSetIdentity`.

## ChangeSet identity

`ChangeSetIdentity` is a versioned SHA-256 identity over the canonical serialized
semantic publication payload.

The identity binds:

- base revision;
- branch name;
- commit message;
- file paths;
- operations;
- file contents.

Change ordering is canonicalized by repository-relative path before hashing, so
ordering differences that do not change publication semantics do not create a
different identity.

The M12.6 publication smoke observed:

```text
v1:sha256:4c55e4fac272712767c60fac496a23273045f132d857624d5350ef1b4de09ffa
```

## Disposable materialization

Verification does not trust the worker workspace as an authoritative publication
source.

The platform creates a fresh disposable Git workspace from a trusted local baseline,
requires `HEAD == ChangeSet.base_revision`, detaches at that exact revision, removes
the cloned remote, and applies the requested `ChangeSet` as uncommitted changes.

Materialization rejects:

- stale or unexpected base revisions;
- path traversal;
- absolute/noncanonical paths;
- `.git` mutation;
- symlink traversal;
- invalid deletes;
- no-op semantic changes.

The materialized semantic diff is reconstructed and must reproduce the original
`ChangeSetIdentity`.

## Post-verification integrity

Repository tests are untrusted code and may mutate the writable workspace.

Therefore verification success is followed by another exactness check before a
`VerifiedChangeSet` can be issued.

The postcondition requires:

```text
HEAD == original base revision
materialized semantic diff == original ChangeSet
ChangeSetIdentity == original ChangeSetIdentity
```

A mutation of tracked content, Git `HEAD`, or the semantic diff fails closed.

The verification workspace is then discarded. Publication uses the original immutable
`ChangeSet` object bound to the verified identity, not the potentially mutated
verification workspace.

## Verified publication boundary

The supervised coding application path publishes through `VerifiedChangePublisher`.

It accepts a `VerifiedChangeSet`, recomputes its current identity immediately before
delegation, and fails closed if the identity has drifted.

The lower-level `TrustedPublisher` remains responsible for protected-path policy and
the actual trusted sink.

This distinction is intentional:

```text
Coding Agent
!= Verification Authority
!= Publication Authority
!= Merge Authority
```

M12.6 constrains the supervised coding application path. It does not remove the
lower-level trusted publisher API used by trusted control-plane code.

## Hardened verifier boundary

The authoritative M12 V0 profile was executed successfully inside the hardened Docker
verification boundary on `agent01`.

Final verifier image ID:

```text
sha256:74109157bffb9adb5f04ea13f2b227c3152f098bf9609b154f1eb670198f1578
```

Observed controls:

```text
network none                          PASS
read-only container root filesystem  PASS
workspace write required by tests    PASS
.git mounted read-only               PASS
Docker/publisher sockets absent       PASS
NoNewPrivs = 1                       PASS
effective capabilities = 0           PASS
```

The container also runs with explicit PID, memory, and CPU limits and without
publication/model-gateway credentials.

`/tmp` is a tmpfs with `exec,nosuid,nodev`. `exec` is required because the repository
test suite creates and executes temporary fake CLI programs. This does not add a new
code-execution authority: authoritative verification already intentionally executes
untrusted repository code. Isolation is enforced by the surrounding Docker boundary,
not by `/tmp noexec`.

## Offline authoritative verification

The verifier retains `--network none`.

Two compatibility requirements were measured and addressed without restoring network
access:

1. subprocess tests require `PYTHONPATH=/workspace/src`;
2. `python -m build` creates an isolated build environment that needs
   `setuptools>=75`.

The verifier image therefore contains an offline wheelhouse for build-system
requirements and runs with:

```text
PIP_NO_INDEX=1
PIP_FIND_LINKS=/opt/wheelhouse
PYTHONPATH=/workspace/src
```

The final live authoritative profile result was:

```text
profile_version = m12-v0
profile_outcome = pass
checks          = 7 / 7 pass
```

## Publication binding smoke

The deterministic integration smoke used:

```text
SupervisedCodingService
  -> real ChangeSet materialization
  -> AuthoritativeVerifier with controlled complete PASS evidence
  -> VerifiedChangeSet
  -> VerifiedChangePublisher
  -> TrustedPublisher
  -> real LocalGitChangeSink
  -> real Git commit
```

The controlled verifier in this smoke isolates the publication-binding invariant from
the separate verifier-confinement experiment.

Observed publication assertions:

```text
publication identity == verified identity        PASS
published commit == publication reference        PASS
published parent == trusted base                 PASS
published branch == ChangeSet branch             PASS
published commit message == ChangeSet message    PASS
published paths == ChangeSet paths               PASS
published contents == ChangeSet contents         PASS
trusted baseline remained unchanged              PASS
```

## Repository quality gate

Before final evidence capture, the branch passed:

```text
python -m compileall -q src tests scripts   PASS
python -m ruff check src tests scripts      PASS
python -m ruff format --check src tests scripts
                                             PASS
python -m mypy src                          PASS
python -m pytest -q                         PASS — 482 passed
python -m build                             PASS
git diff --check                            PASS
```

A final full gate is still required after adding the evidence files.

## Security claims and limits

Accepted M12 V0 claims:

- the verifier has no network access;
- the verifier does not receive the publisher socket;
- the verifier does not receive the Docker socket;
- the verifier does not receive publication credentials;
- Git metadata is read-only inside the verifier;
- arbitrary verifier workspace mutations cannot silently change the published
  `ChangeSet`;
- verification failure or malformed evidence cannot produce `VerifiedChangeSet`;
- identity drift before publication fails closed;
- publication still revalidates existing trusted publication policy;
- GitHub CI and human merge authority remain independent later gates.

Explicit non-claims:

- Docker-in-unprivileged-LXC is not claimed to provide VM-equivalent isolation;
- the verifier image build is not claimed to be bit-for-bit reproducible;
- execution pinning by exact image ID does not by itself constitute a full software
  supply-chain attestation;
- M12.6 does not make model-generated code self-governing or self-merging.

## Decision

Accept the M12.6 V0 design:

```text
exact ChangeSet
  -> hardened authoritative verification
  -> post-verification exactness check
  -> VerifiedChangeSet
  -> identity-checked trusted publication
```

The measured verifier threat model justifies the hardened Docker boundary already
available on `agent01`; a microVM verifier remains deferred until evidence shows the
additional isolation is necessary.

M12.6 is ready for final repository gate and PR review.
