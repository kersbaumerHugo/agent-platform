from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_platform.worker.session import (
    WorkerExecutionRequest,
)
from agent_platform.worker.supervisor import (
    SubprocessWorkerExecutor,
    WorkerProcessTimeoutError,
)

OUTSIDE_READ_MARKER = "M12_OUTSIDE_READ_SENTINEL"
OUTSIDE_WRITE_MARKER = "M12_OUTSIDE_WRITE_SENTINEL"
FORBIDDEN_ENV_MARKER = "M12_FORBIDDEN_ENV_SENTINEL"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe the current SubprocessWorkerExecutor boundary with safe, temporary sentinels."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evidence/artifacts/m12-worker-boundary-baseline.json"),
    )
    parser.add_argument(
        "--probe-timeout-seconds",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--hard-timeout-seconds",
        type=float,
        default=0.3,
    )
    return parser.parse_args()


def git_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _attempt_file_read(path: Path) -> bool:
    try:
        return path.read_text(encoding="utf-8") == OUTSIDE_READ_MARKER
    except (OSError, UnicodeError):
        return False


def _attempt_file_write(path: Path) -> bool:
    try:
        path.write_text(
            OUTSIDE_WRITE_MARKER,
            encoding="utf-8",
        )
    except OSError:
        return False

    try:
        return path.read_text(encoding="utf-8") == OUTSIDE_WRITE_MARKER
    except (OSError, UnicodeError):
        return False


def _attempt_unix_socket(path: Path) -> bool:
    client = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )
    client.settimeout(1.0)

    try:
        client.connect(str(path))
    except OSError:
        return False
    finally:
        client.close()

    return True


def _attempt_tcp_loopback(port: int) -> bool:
    try:
        with socket.create_connection(
            ("127.0.0.1", port),
            timeout=1.0,
        ):
            return True
    except OSError:
        return False


def child_probe(
    *,
    outside_read: Path,
    outside_write: Path,
    unix_socket: Path,
    tcp_port: int,
) -> int:
    workspace_write = False

    try:
        workspace_target = Path.cwd() / "m12-workspace-write.txt"
        workspace_target.write_text(
            "workspace write allowed\n",
            encoding="utf-8",
        )
        workspace_write = workspace_target.exists()
    except OSError:
        pass

    result = {
        "workspace_write_allowed": workspace_write,
        "outside_workspace_read_allowed": _attempt_file_read(
            outside_read,
        ),
        "outside_workspace_write_allowed": _attempt_file_write(
            outside_write,
        ),
        "forbidden_env_visible": (
            os.environ.get("M12_FORBIDDEN_ENV_SENTINEL") == FORBIDDEN_ENV_MARKER
        ),
        "unix_socket_connect_allowed": _attempt_unix_socket(
            unix_socket,
        ),
        "tcp_loopback_connect_allowed": _attempt_tcp_loopback(
            tcp_port,
        ),
    }

    sys.stdout.write(
        json.dumps(
            result,
            sort_keys=True,
        )
    )
    sys.stdout.write("\n")
    return 0


async def run_boundary_probe(
    *,
    script_path: Path,
    workspace: Path,
    outside_read: Path,
    outside_write: Path,
    unix_socket: Path,
    tcp_port: int,
    timeout_seconds: float,
) -> dict[str, bool]:
    def command_factory(
        _: Path,
    ) -> tuple[str, ...]:
        return (
            sys.executable,
            str(script_path),
            "--child",
            "--outside-read",
            str(outside_read),
            "--outside-write",
            str(outside_write),
            "--unix-socket",
            str(unix_socket),
            "--tcp-port",
            str(tcp_port),
        )

    env = {
        "PATH": os.environ.get("PATH", ""),
        "M12_FORBIDDEN_ENV_SENTINEL": FORBIDDEN_ENV_MARKER,
    }

    executor = SubprocessWorkerExecutor(
        command_factory=command_factory,
        timeout_seconds=timeout_seconds,
        terminate_grace_seconds=0.2,
        env=env,
    )

    result = await executor.execute(
        WorkerExecutionRequest(
            goal="Run safe M12 boundary probes.",
            workspace=workspace,
        )
    )

    decoded = json.loads(result.summary)

    if not isinstance(decoded, dict):
        raise RuntimeError("Boundary probe returned a non-object payload.")

    return {key: bool(value) for key, value in decoded.items()}


async def run_timeout_probe(
    *,
    script_path: Path,
    workspace: Path,
    timeout_seconds: float,
) -> bool:
    def command_factory(
        _: Path,
    ) -> tuple[str, ...]:
        return (
            sys.executable,
            str(script_path),
            "--sleep-child",
        )

    executor = SubprocessWorkerExecutor(
        command_factory=command_factory,
        timeout_seconds=timeout_seconds,
        terminate_grace_seconds=0.2,
        env={
            "PATH": os.environ.get("PATH", ""),
        },
    )

    try:
        await executor.execute(
            WorkerExecutionRequest(
                goal="Exercise the hard timeout.",
                workspace=workspace,
            )
        )
    except WorkerProcessTimeoutError:
        return True

    return False


def classify(
    probe: dict[str, bool],
    *,
    hard_timeout_enforced: bool,
) -> dict[str, Any]:
    violations = {
        "outside_workspace_read": probe["outside_workspace_read_allowed"],
        "outside_workspace_write": probe["outside_workspace_write_allowed"],
        "forbidden_env_visibility": probe["forbidden_env_visible"],
        "direct_unix_socket_connect": probe["unix_socket_connect_allowed"],
        "unrestricted_host_tcp_connect": probe["tcp_loopback_connect_allowed"],
    }

    baseline_accepted = (
        probe["workspace_write_allowed"] and hard_timeout_enforced and not any(violations.values())
    )

    return {
        "baseline_accepted": baseline_accepted,
        "decision": (
            "baseline_sufficient" if baseline_accepted else "stronger_execution_boundary_required"
        ),
        "violations": violations,
    }


async def parent_probe(
    args: argparse.Namespace,
) -> int:
    script_path = Path(__file__).resolve()

    with tempfile.TemporaryDirectory(
        prefix="m12-boundary-",
    ) as temp_dir:
        root = Path(temp_dir)
        workspace = root / "workspace"
        outside = root / "outside"

        workspace.mkdir()
        outside.mkdir()

        outside_read = outside / "read-sentinel.txt"
        outside_read.write_text(
            OUTSIDE_READ_MARKER,
            encoding="utf-8",
        )

        outside_write = outside / "write-sentinel.txt"
        unix_socket_path = outside / "publisher.sock"

        unix_listener = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )
        unix_listener.bind(str(unix_socket_path))
        unix_listener.listen(1)

        tcp_listener = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )
        tcp_listener.bind(
            ("127.0.0.1", 0),
        )
        tcp_listener.listen(1)

        tcp_port = int(
            tcp_listener.getsockname()[1],
        )

        try:
            probe = await run_boundary_probe(
                script_path=script_path,
                workspace=workspace,
                outside_read=outside_read,
                outside_write=outside_write,
                unix_socket=unix_socket_path,
                tcp_port=tcp_port,
                timeout_seconds=args.probe_timeout_seconds,
            )

            hard_timeout_enforced = await run_timeout_probe(
                script_path=script_path,
                workspace=workspace,
                timeout_seconds=args.hard_timeout_seconds,
            )
        finally:
            tcp_listener.close()
            unix_listener.close()

        classification = classify(
            probe,
            hard_timeout_enforced=hard_timeout_enforced,
        )

        artifact = {
            "suite_id": "m12-worker-boundary-baseline-v0",
            "captured_at": datetime.now(UTC).isoformat(),
            "git_revision": git_revision(),
            "platform": platform.system().lower(),
            "executor": "SubprocessWorkerExecutor",
            "probe": {
                **probe,
                "hard_timeout_enforced": hard_timeout_enforced,
            },
            **classification,
            "raw_secret_values_included": False,
            "raw_host_file_contents_included": False,
        }

    serialized = json.dumps(
        artifact,
        indent=2,
        sort_keys=True,
    )

    print(serialized)

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.output.write_text(
        serialized + "\n",
        encoding="utf-8",
    )

    return 0


def child_args(
    argv: list[str],
) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outside-read", type=Path, required=True)
    parser.add_argument("--outside-write", type=Path, required=True)
    parser.add_argument("--unix-socket", type=Path, required=True)
    parser.add_argument("--tcp-port", type=int, required=True)
    return parser.parse_args(argv)


def main() -> None:
    argv = sys.argv[1:]

    if argv and argv[0] == "--child":
        args = child_args(argv[1:])
        raise SystemExit(
            child_probe(
                outside_read=args.outside_read,
                outside_write=args.outside_write,
                unix_socket=args.unix_socket,
                tcp_port=args.tcp_port,
            )
        )

    if argv == ["--sleep-child"]:
        import time

        time.sleep(60)
        raise SystemExit(0)

    args = parse_args()
    raise SystemExit(
        asyncio.run(
            parent_probe(args),
        )
    )


if __name__ == "__main__":
    main()
