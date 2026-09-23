# M15 — Trusted Developer Agent V1 Results

## Objective

Prove that the Agent Platform can perform real supervised self-development
without granting the agent Docker authority, publisher credentials or automatic
merge authority.

## Accepted trust boundary

```text
Task
  ↓
developer-agent
  ↓
ToolCallingRuntime
  ↓
repository_inspect / coding_execute
  ↓
trusted sandbox over Unix socket
  ↓
coding Worker
  ↓
ChangeSet
  ↓
authoritative verifier over Unix socket
  ↓
VerifiedChangeSet
  ↓
trusted publisher over Unix socket
  ↓
GitHub Pull Request
  ↓
CI
  ↓
human merge
```

## Identity model

Configured runtime identity:

```text
developer-agent
```

Trusted authorization principal:

```text
agent:developer-agent
```

The request `agent_id` confirms the configured runtime identity. It is not an
authorization principal and cannot grant capabilities.

## Docker authority

The non-root `agent-platform` API process has no Docker authority.

Docker is owned only by:

- the trusted coding sandbox daemon;
- the trusted authoritative verifier daemon.

Both are reached through Unix sockets.

## Coding sandbox

Validated coding image:

```text
sha256:27fc10067e66f28a0644a7bcfa490f3e613e46f6b7846b456e773fbb31ffa1ee
```

Validated sandbox properties:

- network disabled;
- read-only root filesystem;
- non-root Worker;
- all Linux capabilities dropped;
- no-new-privileges;
- bounded CPU, memory and PID count;
- disposable workspace;
- no Docker socket;
- no publisher socket;
- Model Gateway reachable only through a trusted Unix-socket credential relay;
- DeepSeek Harness `sdk-minimal`;
- `deepseek-harness-sdk==0.1.5rc1`;
- 16 MiB ephemeral `/tmp`.

The `/tmp` mount requires `exec` because the pinned DSH runtime loads native
modules from its ephemeral cache. `nosuid` and `nodev` remain enabled.

## Authoritative verification

Validated verifier image:

```text
sha256:74109157bffb9adb5f04ea13f2b227c3152f098bf9609b154f1eb670198f1578
```

Verification is isolated behind a trusted Unix socket. Docker authority is not
present in the API process.

The accepted invariant remains:

```text
trusted base
→ exact ChangeSet
→ authoritative verification
→ SAME ChangeSet
→ trusted publication
```

## First production self-development run

Run:

```text
dd91cc8f-4fbf-48c4-9ed6-6343c3ef7ab3
```

Result:

```text
status=succeeded
```

The Worker changed only `README.md`.

Verification:

```text
profile=m12-v0
outcome=PASS
```

Publication created:

```text
PR #84
```

GitHub CI completed successfully.

The pull request was merged manually by a human. No auto-merge authority was
granted to the agent.

This first run proved supervised self-development, but the exact base revision
was supplied directly to `coding_execute` because the runtime still supported
only one model tool-call round.

## Deployment-as-code closure

After merging the initial M15 implementation, the production host was rebuilt
from the Git-tracked release and systemd units.

That reproduction exposed one configuration drift: the API unit did not
explicitly select the local model provider and therefore fell back to the
OpenRouter default.

The versioned API unit was corrected to define:

```text
MODEL_PROVIDER=local
LOCAL_MODEL_BASE_URL=http://192.168.10.40:8080/v1
LOCAL_MODEL_NAME=qwen3.5-9b-local
LOCAL_MODEL_TIMEOUT_SECONDS=180
```

The model API key remains outside Git in `/etc/agent-platform/m15.env`.

This operational reproduction converted the previously manual deployment state
into a Git-reproducible M15 deployment definition.

## M15.6 — Bounded Multi-Round Tool Loop

M15.6 replaced the one-round runtime limitation with a hard upper bound of two
model tool-call rounds.

The accepted runtime shape is:

```text
model
  ↓
tool round 1
  ↓
tool result returned to model
  ↓
tool round 2
  ↓
tool result returned to model
  ↓
final model response with tools disabled
```

The runtime fails closed if the model requests another tool after the configured
two-round limit.

The limit is intentionally fixed in V1 rather than exposed as another runtime
configuration surface.

## RepoWise production integration findings

The first M15.6 production attempt failed closed during `repository_inspect`
because the trusted repository had no RepoWise index.

Production bootstrap therefore requires a RepoWise index for the trusted
repository before repository inspection can be used.

The second production finding was a representation mismatch:

```text
RepoWise indexed_commit: 12-character abbreviated Git revision
coding_execute contract: full 40-character Git SHA-1
```

The RepoWise adapter now resolves the provider revision against the trusted
repository using Git and exposes the full commit SHA to platform consumers.

If the provider revision cannot be resolved to a full commit, the adapter fails
closed.

The strict `coding_execute.expected_base_revision` contract remains unchanged.

## M15.6 production self-development run

The final production validation was executed without supplying a Git SHA in the
task prompt.

Run:

```text
c66f9473-ff05-422b-8b09-0253617c656b
```

Starting base revision:

```text
7072c45fc95f71c99a7994cc46cd268882f24d7a
```

Task:

```text
Inspect README.md first.
Use the repository evidence to determine the exact base revision.
Then update the outdated one-round runtime statement to the new hard
two-round tool-call limit without unrelated changes.
```

Observed path:

```text
repository_inspect
  ↓
RepoWise evidence + abbreviated indexed commit
  ↓
adapter resolves full Git SHA
  ↓
model reasons over returned tool evidence
  ↓
coding_execute(expected_base_revision=<full SHA>)
  ↓
trusted sandbox
  ↓
authoritative verification
  ↓
trusted publisher
  ↓
PR #89
```

Result:

```text
status=succeeded
changed_paths=README.md
base_revision=7072c45fc95f71c99a7994cc46cd268882f24d7a
pull_request=89
```

PR #89 contained one targeted file change with one addition and one deletion.

The pull request was merged manually by a human.

Main after merge:

```text
ccff6a93833385c8d749090e446304c511d86d1b
```

## Runtime timing evidence

The production run completed in approximately 529 seconds.

Observed main-run timings included:

```text
repository_inspect ≈ 3.64 s
model reasoning before coding_execute ≈ 58.70 s
coding_execute ≈ 323.94 s
final model response ≈ 129.87 s
```

The evidence does not point to repository inspection or platform tool
orchestration as the dominant latency source. Most elapsed time was spent in
coding execution and model inference.

No additional platform abstraction was introduced in response to this timing
evidence.

## Operational closure

The final M15 production state retains:

```text
current release:
m15-ccff6a938333

known rollback release:
m15-7072c45fc95f
```

The trusted repository, runtime release and RepoWise index were aligned to the
production Git revision during final cleanup.

The M15 services remain enabled and active:

```text
agent-platform-m15-sandbox
agent-platform-m15-verifier
agent-platform-m15-api
```

## Result

M15 and M15.6 demonstrated a real bounded self-development path:

```text
inspect
→ reason
→ code
→ verify
→ publish
→ human merge
```

The agent obtained its own repository evidence and exact base revision instead
of receiving the revision in the prompt.

The mechanisms deciding promotion remained outside agent authority throughout
the flow.

## Closure

```text
M15   Trusted Developer Agent V1        CLOSED
M15.6 Bounded Multi-Round Tool Loop     CLOSED
Real self-development E2E               PASS
Human merge authority                   PRESERVED
```

Further platform complexity should require new evidence rather than extending
this trust boundary speculatively.
