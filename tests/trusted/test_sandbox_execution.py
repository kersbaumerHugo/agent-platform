from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from agent_platform.trust.sandbox_execution import (
    SandboxExecutionRequest,
    SandboxExecutionRequestError,
    TrustedWorkspaceError,
    TrustedWorkspaceResolver,
    deserialize_sandbox_execution_request,
    serialize_sandbox_execution_request,
)

EXECUTION_ID = UUID("8c1b2329-1907-45a0-8a76-971ca62283ae")


def example_request() -> SandboxExecutionRequest:
    return SandboxExecutionRequest(
        execution_id=EXECUTION_ID,
        workspace_name="worker-example",
        goal="Update the requested file.",
    )


def test_request_round_trip_is_deterministic() -> None:
    request = example_request()

    encoded = serialize_sandbox_execution_request(request)

    assert encoded == (serialize_sandbox_execution_request(request))
    assert deserialize_sandbox_execution_request(encoded) == request


@pytest.mark.parametrize(
    "extra_field",
    [
        "image",
        "command",
        "network",
        "mount_source",
        "uid",
        "docker_flags",
        "credential",
    ],
)
def test_request_rejects_authority_bearing_fields(
    extra_field: str,
) -> None:
    payload = json.loads(serialize_sandbox_execution_request(example_request()))
    payload[extra_field] = "attacker-controlled"

    with pytest.raises(
        SandboxExecutionRequestError,
        match="unexpected fields",
    ):
        deserialize_sandbox_execution_request(json.dumps(payload))


def test_request_rejects_invalid_protocol_version() -> None:
    payload = json.loads(serialize_sandbox_execution_request(example_request()))
    payload["version"] = 2

    with pytest.raises(
        SandboxExecutionRequestError,
        match="Unsupported",
    ):
        deserialize_sandbox_execution_request(json.dumps(payload))


def test_request_normalizes_intent_strings() -> None:
    request = SandboxExecutionRequest(
        execution_id=EXECUTION_ID,
        workspace_name="  worker-example  ",
        goal="  Fix the test.  ",
    )

    assert request.workspace_name == "worker-example"
    assert request.goal == "Fix the test."


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not-json",
        "[]",
        "{}",
    ],
)
def test_request_rejects_invalid_envelope(
    raw: str,
) -> None:
    with pytest.raises(SandboxExecutionRequestError):
        deserialize_sandbox_execution_request(raw)


def test_resolver_accepts_existing_direct_child(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    workspace = root / "worker-abc123"
    workspace.mkdir()

    resolver = TrustedWorkspaceResolver(
        workspace_root=root,
    )

    assert resolver.resolve("worker-abc123") == workspace.resolve()


@pytest.mark.parametrize(
    "workspace_name",
    [
        "../outside",
        "/tmp/outside",
        "nested/workspace",
        "worker\\escape",
        ".",
        "..",
        "worker name",
    ],
)
def test_resolver_rejects_non_child_names(
    tmp_path: Path,
    workspace_name: str,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    resolver = TrustedWorkspaceResolver(
        workspace_root=root,
    )

    with pytest.raises(TrustedWorkspaceError):
        resolver.resolve(workspace_name)


def test_resolver_rejects_workspace_symlink_escape(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()

    (root / "worker-link").symlink_to(
        outside,
        target_is_directory=True,
    )

    resolver = TrustedWorkspaceResolver(
        workspace_root=root,
    )

    with pytest.raises(
        TrustedWorkspaceError,
        match="symlink",
    ):
        resolver.resolve("worker-link")


def test_resolver_rejects_missing_workspace(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    resolver = TrustedWorkspaceResolver(
        workspace_root=root,
    )

    with pytest.raises(
        TrustedWorkspaceError,
        match="does not exist",
    ):
        resolver.resolve("worker-missing")


def test_resolver_rejects_file_instead_of_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()

    (root / "worker-file").write_text(
        "not a directory",
        encoding="utf-8",
    )

    resolver = TrustedWorkspaceResolver(
        workspace_root=root,
    )

    with pytest.raises(
        TrustedWorkspaceError,
        match="directory",
    ):
        resolver.resolve("worker-file")


def test_resolver_rejects_symlink_workspace_root(
    tmp_path: Path,
) -> None:
    real_root = tmp_path / "real-workspaces"
    real_root.mkdir()

    linked_root = tmp_path / "workspaces"
    linked_root.symlink_to(
        real_root,
        target_is_directory=True,
    )

    with pytest.raises(
        TrustedWorkspaceError,
        match="workspace_root",
    ):
        TrustedWorkspaceResolver(
            workspace_root=linked_root,
        )
