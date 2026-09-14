import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from agent_platform.trust.change_request import (
    serialize_change_set,
)
from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
)
from agent_platform.trust.runtime import build_server


def git(
    repo: Path,
    *args: str,
) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    return result.stdout.strip()


@pytest.fixture
def trusted_repo(
    tmp_path: Path,
) -> tuple[Path, str]:
    repo = tmp_path / "trusted-repo"
    repo.mkdir()

    git(repo, "init", "-b", "main")

    (repo / "README.md").write_text(
        "# trusted test\n",
        encoding="utf-8",
    )

    git(repo, "add", "README.md")

    git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "initial",
    )

    return repo, git(repo, "rev-parse", "HEAD")


async def send_request(
    socket_path: Path,
    change_set: ChangeSet,
) -> dict[str, object]:
    reader, writer = await asyncio.open_unix_connection(socket_path)

    writer.write(serialize_change_set(change_set).encode("utf-8") + b"\n")

    await writer.drain()

    response = json.loads(await reader.readline())

    writer.close()
    await writer.wait_closed()

    return response


@pytest.mark.asyncio
async def test_runtime_publishes_allowed_change(
    tmp_path: Path,
    trusted_repo: tuple[Path, str],
) -> None:
    repo, base_revision = trusted_repo
    socket_path = tmp_path / "publisher.sock"

    server = build_server(
        socket_path=socket_path,
        repo_root=repo,
    )

    await server.start()

    try:
        response = await send_request(
            socket_path,
            ChangeSet(
                base_revision=base_revision,
                branch_name="agent/runtime-test",
                commit_message="feat: runtime test",
                changes=(
                    FileChange(
                        path="src/example.py",
                        operation=FileChangeOperation.UPSERT,
                        content="VALUE = 42\n",
                    ),
                ),
            ),
        )
    finally:
        await server.close()

    assert response["status"] == "accepted"

    assert (
        git(
            repo,
            "branch",
            "--show-current",
        )
        == "agent/runtime-test"
    )

    assert (repo / "src/example.py").read_text(encoding="utf-8") == "VALUE = 42\n"


@pytest.mark.asyncio
async def test_runtime_rejects_gate_change_without_git_mutation(
    tmp_path: Path,
    trusted_repo: tuple[Path, str],
) -> None:
    repo, base_revision = trusted_repo
    socket_path = tmp_path / "publisher.sock"

    server = build_server(
        socket_path=socket_path,
        repo_root=repo,
    )

    await server.start()

    try:
        response = await send_request(
            socket_path,
            ChangeSet(
                base_revision=base_revision,
                branch_name="agent/attack",
                commit_message="chore: weaken gates",
                changes=(
                    FileChange(
                        path=".github/workflows/ci.yml",
                        operation=FileChangeOperation.UPSERT,
                        content="name: bypass\n",
                    ),
                ),
            ),
        )
    finally:
        await server.close()

    assert response["status"] == "rejected"
    assert response["reason_code"] == "protected_path_modified"

    assert (
        git(
            repo,
            "branch",
            "--show-current",
        )
        == "main"
    )

    assert git(repo, "rev-parse", "HEAD") == base_revision

    assert not (repo / ".github/workflows/ci.yml").exists()


@pytest.mark.asyncio
async def test_github_runtime_pushes_branch_and_creates_pr(
    tmp_path: Path,
) -> None:
    from agent_platform.trust.runtime import (
        build_github_server,
    )

    remote = tmp_path / "remote.git"

    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
        text=True,
    )

    repo = tmp_path / "trusted-github-repo"
    repo.mkdir()

    git(repo, "init", "-b", "main")

    (repo / "README.md").write_text(
        "# trusted github test\n",
        encoding="utf-8",
    )

    git(repo, "add", "README.md")

    git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "initial",
    )

    git(
        repo,
        "remote",
        "add",
        "origin",
        str(remote),
    )

    git(
        repo,
        "push",
        "-u",
        "origin",
        "main",
    )

    base_revision = git(
        repo,
        "rev-parse",
        "HEAD",
    )

    fake_gh = tmp_path / "gh"

    fake_gh.write_text(
        """#!/bin/sh
printf '%s\\n' \
'https://github.com/kersbaumerHugo/agent-platform/pull/999'
""",
        encoding="utf-8",
    )

    fake_gh.chmod(0o755)

    socket_path = tmp_path / "publisher.sock"

    server = build_github_server(
        socket_path=socket_path,
        repo_root=repo,
        repository="kersbaumerHugo/agent-platform",
        gh_binary=str(fake_gh),
    )

    await server.start()

    try:
        response = await send_request(
            socket_path,
            ChangeSet(
                base_revision=base_revision,
                branch_name="agent/github-runtime-test",
                commit_message="docs: github runtime test",
                changes=(
                    FileChange(
                        path="docs/github-runtime.md",
                        operation=FileChangeOperation.UPSERT,
                        content="# GitHub Runtime\n",
                    ),
                ),
            ),
        )
    finally:
        await server.close()

    assert response == {
        "reference": ("https://github.com/kersbaumerHugo/agent-platform/pull/999"),
        "status": "accepted",
    }

    pushed_revision = subprocess.run(
        [
            "git",
            "--git-dir",
            str(remote),
            "rev-parse",
            "refs/heads/agent/github-runtime-test",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert pushed_revision != base_revision

    remote_main = subprocess.run(
        [
            "git",
            "--git-dir",
            str(remote),
            "rev-parse",
            "refs/heads/main",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert remote_main == base_revision
