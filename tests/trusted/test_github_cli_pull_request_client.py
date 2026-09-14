import json
from pathlib import Path

import pytest

from agent_platform.adapters.github.cli import (
    GitHubCliError,
    GitHubCliPullRequestClient,
)
from agent_platform.adapters.github.proposal import (
    PullRequestSpec,
)


def make_fake_gh(
    tmp_path: Path,
    *,
    exit_code: int = 0,
    stdout: str = ("https://github.com/kersbaumerHugo/agent-platform/pull/42"),
    stderr: str = "",
) -> tuple[Path, Path, Path]:
    argv_file = tmp_path / "argv.json"
    stdin_file = tmp_path / "stdin.txt"
    executable = tmp_path / "gh"

    executable.write_text(
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

Path({str(argv_file)!r}).write_text(
    json.dumps(sys.argv[1:]),
    encoding="utf-8",
)

Path({str(stdin_file)!r}).write_text(
    sys.stdin.read(),
    encoding="utf-8",
)

sys.stdout.write({stdout!r})
sys.stderr.write({stderr!r})
raise SystemExit({exit_code})
""",
        encoding="utf-8",
    )

    executable.chmod(0o755)

    return executable, argv_file, stdin_file


@pytest.mark.asyncio
async def test_creates_pull_request_with_narrow_command(
    tmp_path: Path,
) -> None:
    gh, argv_file, stdin_file = make_fake_gh(tmp_path)

    client = GitHubCliPullRequestClient(
        "kersbaumerHugo/agent-platform",
        gh_binary=str(gh),
    )

    spec = PullRequestSpec(
        head_branch="agent/example",
        base_branch="main",
        title="feat: example",
        body="trusted body\n",
    )

    result = await client.create_pull_request(spec)

    assert result.reference == ("https://github.com/kersbaumerHugo/agent-platform/pull/42")

    argv = json.loads(argv_file.read_text(encoding="utf-8"))

    assert argv == [
        "pr",
        "create",
        "--repo",
        "kersbaumerHugo/agent-platform",
        "--base",
        "main",
        "--head",
        "agent/example",
        "--title",
        "feat: example",
        "--body-file",
        "-",
    ]

    assert stdin_file.read_text(encoding="utf-8") == "trusted body\n"


@pytest.mark.asyncio
async def test_body_is_not_exposed_in_process_arguments(
    tmp_path: Path,
) -> None:
    gh, argv_file, _ = make_fake_gh(tmp_path)

    client = GitHubCliPullRequestClient(
        "kersbaumerHugo/agent-platform",
        gh_binary=str(gh),
    )

    secret_marker = "body-must-not-be-in-argv"

    await client.create_pull_request(
        PullRequestSpec(
            head_branch="agent/example",
            base_branch="main",
            title="feat: example",
            body=secret_marker,
        )
    )

    argv = json.loads(argv_file.read_text(encoding="utf-8"))

    assert secret_marker not in argv


@pytest.mark.asyncio
async def test_cli_failure_is_reported(
    tmp_path: Path,
) -> None:
    gh, _, _ = make_fake_gh(
        tmp_path,
        exit_code=1,
        stdout="",
        stderr="simulated failure",
    )

    client = GitHubCliPullRequestClient(
        "kersbaumerHugo/agent-platform",
        gh_binary=str(gh),
    )

    with pytest.raises(
        GitHubCliError,
        match="simulated failure",
    ):
        await client.create_pull_request(
            PullRequestSpec(
                head_branch="agent/example",
                base_branch="main",
                title="feat: example",
                body="body",
            )
        )


@pytest.mark.asyncio
async def test_unexpected_cli_output_is_rejected(
    tmp_path: Path,
) -> None:
    gh, _, _ = make_fake_gh(
        tmp_path,
        stdout="unexpected output",
    )

    client = GitHubCliPullRequestClient(
        "kersbaumerHugo/agent-platform",
        gh_binary=str(gh),
    )

    with pytest.raises(
        GitHubCliError,
        match="unexpected PR reference",
    ):
        await client.create_pull_request(
            PullRequestSpec(
                head_branch="agent/example",
                base_branch="main",
                title="feat: example",
                body="body",
            )
        )


@pytest.mark.parametrize(
    "repository",
    [
        "",
        "agent-platform",
        "owner/repo/extra",
        "-owner/repo",
        "owner/-repo",
        "owner repo/repo",
    ],
)
def test_rejects_invalid_repository(
    repository: str,
) -> None:
    with pytest.raises(ValueError):
        GitHubCliPullRequestClient(repository)


@pytest.mark.asyncio
async def test_rejects_option_like_branch_name(
    tmp_path: Path,
) -> None:
    gh, _, _ = make_fake_gh(tmp_path)

    client = GitHubCliPullRequestClient(
        "kersbaumerHugo/agent-platform",
        gh_binary=str(gh),
    )

    with pytest.raises(
        ValueError,
        match="head_branch",
    ):
        await client.create_pull_request(
            PullRequestSpec(
                head_branch="--admin",
                base_branch="main",
                title="feat: example",
                body="body",
            )
        )
