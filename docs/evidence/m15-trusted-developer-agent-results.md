# M15 — Trusted Developer Agent V1 Results

## Objective

Prove that the Agent Platform can perform one real supervised self-development
task without granting the agent Docker authority, publisher credentials or
automatic merge authority.

## Accepted trust boundary

```text
Task
  ↓
developer-agent
  ↓
ToolCallingRuntime
  ↓
coding.execute
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

## Result

M15 demonstrated a real self-development path in which the agent can propose,
execute, verify and publish a code change while the mechanisms deciding
promotion remain outside agent authority.

## Remaining bounded-runtime limitation

The current `ToolCallingRuntime` permits one model tool-call round.

The first M15 production run therefore supplied the exact expected base revision
directly to `coding.execute`.

A future bounded multi-round runtime may be justified to support:

```text
repository.inspect
→ reason over evidence
→ coding.execute
```

without removing the exact base-revision requirement or introducing an
unbounded autonomous loop.

## Deployment-as-code closure

After merging M15, the production host was rebuilt from the Git-tracked release
and systemd units.

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
