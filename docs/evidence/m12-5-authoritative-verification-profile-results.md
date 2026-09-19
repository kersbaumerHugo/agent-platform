# M12.5 — Authoritative Verification Profile V0

Status: Accepted for M12 V0 evidence

## Decision

M12.5 defines a platform-owned authoritative verification profile that is independent from model self-reporting.

The coding model may run checks for feedback, but only the platform-owned profile determines whether a coding proposal has authoritative verification evidence.

The fixed V0 profile is:

```text
syntax       -> python -m compileall -q src tests scripts
ruff_lint    -> python -m ruff check src tests scripts
ruff_format  -> python -m ruff format --check src tests scripts
typecheck    -> python -m mypy src
test         -> python -m pytest -q
package      -> python -m build
diff_check   -> git diff --check
```

Profile version:

```text
m12-v0
```

## Authority invariant

```text
Coding Agent
!= Verification Authority
!= Publication Authority
!= Merge Authority
```

The model does not select, remove, reorder, or replace authoritative checks.

## Contract

The verification boundary now has explicit contracts for:

- `AuthoritativeVerificationProfile`
- `VerificationStep`
- `VerificationCheck`
- `VerificationOutcome`
- `VerificationStepResult`
- `VerificationResult`
- `VerificationExecutor`
- `AuthoritativeVerifier`
- `ProfileVerificationExecutor`
- `VerificationProcessRunner`

The profile is immutable from caller input.

Verification commands are represented as argv tuples and are executed without a shell.

## Fail-closed evidence validation

`AuthoritativeVerifier` accepts executor evidence only when:

1. the returned profile version exactly matches the platform-owned profile;
2. every authoritative check is present;
3. no check is omitted;
4. no check is duplicated;
5. checks appear in the exact authoritative order.

A verification `FAIL` remains valid evidence when the full profile was actually executed.

Malformed or incomplete evidence is rejected rather than interpreted as success.

## Outcome semantics

```text
PASS
  Every authoritative check executed and passed.

FAIL
  Verification completed, at least one check returned non-zero, and no executor
  error occurred.

ERROR
  At least one verification step could not complete authoritatively, for example
  timeout or execution failure.
```

## Evidence handling

Per-step summaries are bounded by contract.

The current process executor does not capture or persist raw stdout/stderr into verification evidence. It emits bounded reason summaries such as:

```text
verification_step_passed
verification_step_failed
verification_step_timeout
verification_step_execution_error
```

This avoids treating arbitrary untrusted command output as trusted evidence and reduces accidental secret leakage.

## Process execution properties

`SubprocessVerificationProcessRunner` provides:

- argv execution without a shell;
- hard timeout;
- dedicated process group;
- cancellation cleanup;
- minimal explicit environment;
- no forwarding of common publication/model credentials;
- no stdin;
- no raw stdout/stderr propagation into evidence.

Important:

`SubprocessVerificationProcessRunner` is a process-lifecycle primitive, not a filesystem or network isolation boundary.

M12.5 does **not** claim that host subprocess execution is sufficient confinement for untrusted repository code.

Before authoritative verification can authorize publication, the executor must be composed with an execution boundary appropriate for untrusted code and without publication credentials.

That integration remains mandatory for the following M12 publication/integrity work.

## Integrated smoke

The integrated smoke executed:

```text
AuthoritativeVerifier
  -> ProfileVerificationExecutor
  -> SubprocessVerificationProcessRunner
  -> m12-v0 authoritative profile
```

Observed result:

```text
profile_version = m12-v0
outcome         = pass
reason_code     = all_checks_passed
checks          = 7 / 7 pass
```

The smoke proves profile orchestration and evidence validation behavior.

It does not prove verifier sandbox confinement.

## Verification gates

Targeted gates:

```text
verification profile tests       -> 4 passed
verification contract tests      -> 7 passed
authoritative verifier tests     -> 5 passed
verification executor tests      -> 7 passed
```

Integrated authoritative smoke:

```text
7 / 7 authoritative checks passed
```

Full repository quality gate:

```text
python -m compileall -q src tests scripts   PASS
python -m ruff check src tests scripts      PASS
python -m ruff format --check src tests scripts
                                             PASS
python -m mypy src                          PASS
python -m pytest -q                         PASS — 452 passed
python -m build                             PASS
git diff --check                            PASS
```

The smoke script was also type-checked against the local source tree using:

```text
MYPYPATH=src python -m mypy scripts/run_m12_authoritative_verification_smoke.py
```

and passed.

## Accepted properties

M12.5 accepts the following V0 properties:

- authoritative checks are platform-owned;
- callers cannot relax the fixed profile;
- model self-report is non-authoritative;
- commands are argv, not shell strings;
- executor evidence must exactly prove the full profile;
- verification outcomes distinguish pass, fail, and execution error;
- verification evidence is bounded and does not persist raw command output;
- common ambient credentials are not forwarded by the process runner;
- timeouts and cancellation have explicit lifecycle handling.

## Deferred integration requirement

M12.5 intentionally does not publish a `ChangeSet`.

The next integrity step must prove the relationship:

```text
trusted base
  -> exact ChangeSet
  -> materialized verification workspace
  -> authoritative verification
  -> same verified ChangeSet
  -> trusted publisher
```

The verified proposal must not be silently replaced, rebased, mutated, or regenerated before publication.

## Decision

Accept the immutable `m12-v0` authoritative verification profile and its verification contracts/controller as the M12.5 baseline.

Do not treat host subprocess execution as a sufficient untrusted-code security boundary.

Verification confinement and exact verified-ChangeSet publication integrity remain mandatory before publication authority is connected.
