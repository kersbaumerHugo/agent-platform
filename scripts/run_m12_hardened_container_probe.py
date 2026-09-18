from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

IMAGE = "python:3.12-slim"
FORBIDDEN_ENV_NAME = "M12_FORBIDDEN_ENV_SENTINEL"
FORBIDDEN_ENV_VALUE = "M12_FORBIDDEN_ENV_VALUE"
OUTSIDE_READ_MARKER = "M12_OUTSIDE_READ_SENTINEL"
OUTSIDE_WRITE_MARKER = "M12_OUTSIDE_WRITE_SENTINEL"

CHILD_CODE = r"""
import json
import os
import socket
import sys
from pathlib import Path

outside_read = Path(sys.argv[1])
outside_write = Path(sys.argv[2])
symlink_escape = Path(sys.argv[3])
unix_socket = Path(sys.argv[4])
tcp_port = int(sys.argv[5])


def file_read_allowed(path: Path) -> bool:
    try:
        return path.read_text(encoding="utf-8") == "M12_OUTSIDE_READ_SENTINEL"
    except (OSError, UnicodeError):
        return False


def file_write_allowed(path: Path) -> bool:
    try:
        path.write_text(
            "M12_OUTSIDE_WRITE_SENTINEL",
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def unix_socket_connect_allowed(path: Path) -> bool:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(0.5)
    try:
        client.connect(str(path))
        return True
    except OSError:
        return False
    finally:
        client.close()


def tcp_connect_allowed(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def write_allowed(path: Path) -> bool:
    try:
        path.write_text("probe\n", encoding="utf-8")
        return True
    except OSError:
        return False


def proc_status_value(name: str) -> str | None:
    for line in Path("/proc/self/status").read_text(
        encoding="utf-8"
    ).splitlines():
        key, separator, value = line.partition(":")
        if separator and key == name:
            return value.strip()
    return None


def read_cgroup(name: str) -> str | None:
    path = Path("/sys/fs/cgroup") / name
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


result = {
    "uid": os.getuid(),
    "gid": os.getgid(),
    "workspace_write_allowed": write_allowed(
        Path("/workspace/m12-workspace-write.txt")
    ),
    "outside_workspace_read_allowed": file_read_allowed(
        outside_read
    ),
    "outside_workspace_write_allowed": file_write_allowed(
        outside_write
    ),
    "symlink_escape_read_allowed": file_read_allowed(
        symlink_escape
    ),
    "forbidden_env_visible": (
        os.environ.get("M12_FORBIDDEN_ENV_SENTINEL")
        == "M12_FORBIDDEN_ENV_VALUE"
    ),
    "unix_socket_connect_allowed": unix_socket_connect_allowed(
        unix_socket
    ),
    "tcp_loopback_connect_allowed": tcp_connect_allowed(
        "127.0.0.1",
        tcp_port,
    ),
    "internet_egress_allowed": tcp_connect_allowed(
        "1.1.1.1",
        443,
    ),
    "docker_socket_visible": Path(
        "/var/run/docker.sock"
    ).exists(),
    "rootfs_write_allowed": write_allowed(
        Path("/m12-rootfs-write.txt")
    ),
    "no_new_privileges": (
        proc_status_value("NoNewPrivs") == "1"
    ),
    "cap_eff": proc_status_value("CapEff"),
    "pids_max": read_cgroup("pids.max"),
    "memory_max": read_cgroup("memory.max"),
    "cpu_max": read_cgroup("cpu.max"),
}

print(json.dumps(result, sort_keys=True))
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure the hardened Docker container candidate used by "
            "M12.3. Run this script on agent01."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Optional JSON artifact path on the execution host. "
            "The artifact is always printed to stdout."
        ),
    )
    parser.add_argument(
        "--probe-timeout-seconds",
        type=float,
        default=10.0,
    )
    parser.add_argument(
        "--hard-timeout-seconds",
        type=float,
        default=0.5,
    )
    return parser.parse_args()


def docker_version() -> str:
    completed = subprocess.run(
        [
            "docker",
            "version",
            "--format",
            "{{.Server.Version}}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def docker_image_present() -> bool:
    completed = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            IMAGE,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def common_docker_args(
    *,
    name: str,
) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--pull=never",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "64",
        "--memory",
        "256m",
        "--cpus",
        "1",
        "--user",
        "65532:65532",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=16m",
    ]


def run_candidate_probe(
    *,
    workspace: Path,
    outside_read: Path,
    outside_write: Path,
    unix_socket: Path,
    tcp_port: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    container_name = f"m12-boundary-{uuid.uuid4().hex[:12]}"

    command = [
        *common_docker_args(name=container_name),
        "--mount",
        f"type=bind,src={workspace},dst=/workspace",
        "--workdir",
        "/workspace",
        IMAGE,
        "python",
        "-c",
        CHILD_CODE,
        str(outside_read),
        str(outside_write),
        "/workspace/m12-symlink-escape.txt",
        str(unix_socket),
        str(tcp_port),
    ]

    env = os.environ.copy()
    env[FORBIDDEN_ENV_NAME] = FORBIDDEN_ENV_VALUE

    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env=env,
    )

    payload = json.loads(completed.stdout.strip())

    if not isinstance(payload, dict):
        raise RuntimeError("Container probe returned a non-object payload.")

    return payload


def container_exists(name: str) -> bool:
    completed = subprocess.run(
        [
            "docker",
            "inspect",
            name,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def run_cleanup_probe(
    *,
    exit_code: int,
) -> tuple[bool, bool]:
    container_name = f"m12-cleanup-{uuid.uuid4().hex[:12]}"

    command = [
        *common_docker_args(name=container_name),
        IMAGE,
        "python",
        "-c",
        f"raise SystemExit({exit_code})",
    ]

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    observed = completed.returncode == exit_code
    cleaned = not container_exists(container_name)

    return observed, cleaned


def run_timeout_probe(
    *,
    timeout_seconds: float,
) -> tuple[bool, bool]:
    container_name = f"m12-timeout-{uuid.uuid4().hex[:12]}"

    command = [
        *common_docker_args(name=container_name),
        IMAGE,
        "python",
        "-c",
        "import time; time.sleep(60)",
    ]

    timeout_enforced = False

    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        timeout_enforced = True
    finally:
        subprocess.run(
            [
                "docker",
                "rm",
                "-f",
                container_name,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    return timeout_enforced, not container_exists(container_name)


def parse_cpu_limit(value: object) -> bool:
    if not isinstance(value, str):
        return False

    parts = value.split()

    if len(parts) != 2:
        return False

    quota, period = parts

    if quota == "max":
        return False

    try:
        quota_value = int(quota)
        period_value = int(period)
    except ValueError:
        return False

    return quota_value > 0 and period_value > 0 and quota_value <= period_value


def classify(
    probe: dict[str, Any],
    *,
    success_exit_observed: bool,
    success_container_cleaned: bool,
    failure_exit_observed: bool,
    failure_container_cleaned: bool,
    hard_timeout_enforced: bool,
    timeout_container_cleaned: bool,
) -> dict[str, Any]:
    pids_limit_enforced = probe.get("pids_max") == "64"
    memory_limit_enforced = probe.get("memory_max") == str(256 * 1024 * 1024)
    cpu_limit_enforced = parse_cpu_limit(probe.get("cpu_max"))
    capabilities_dropped = probe.get("cap_eff") in (
        "0000000000000000",
        "0",
    )

    violations = {
        "outside_workspace_read": bool(probe.get("outside_workspace_read_allowed")),
        "outside_workspace_write": bool(probe.get("outside_workspace_write_allowed")),
        "symlink_escape_read": bool(probe.get("symlink_escape_read_allowed")),
        "forbidden_env_visibility": bool(probe.get("forbidden_env_visible")),
        "direct_unix_socket_connect": bool(probe.get("unix_socket_connect_allowed")),
        "host_tcp_connect": bool(probe.get("tcp_loopback_connect_allowed")),
        "internet_egress": bool(probe.get("internet_egress_allowed")),
        "docker_socket_visibility": bool(probe.get("docker_socket_visible")),
        "rootfs_write": bool(probe.get("rootfs_write_allowed")),
    }

    required_controls = {
        "workspace_write_allowed": (probe.get("workspace_write_allowed") is True),
        "non_root_identity": (probe.get("uid") == 65532 and probe.get("gid") == 65532),
        "no_new_privileges": (probe.get("no_new_privileges") is True),
        "capabilities_dropped": capabilities_dropped,
        "pids_limit_enforced": pids_limit_enforced,
        "memory_limit_enforced": memory_limit_enforced,
        "cpu_limit_enforced": cpu_limit_enforced,
        "success_exit_observed": success_exit_observed,
        "success_container_cleaned": success_container_cleaned,
        "failure_exit_observed": failure_exit_observed,
        "failure_container_cleaned": failure_container_cleaned,
        "hard_timeout_enforced": hard_timeout_enforced,
        "timeout_container_cleaned": (timeout_container_cleaned),
    }

    candidate_accepted = not any(violations.values()) and all(required_controls.values())

    return {
        "candidate_accepted": candidate_accepted,
        "decision": (
            "hardened_container_sufficient_for_m12_v0"
            if candidate_accepted
            else "candidate_requires_hardening_or_stronger_boundary"
        ),
        "violations": violations,
        "required_controls": required_controls,
    }


def main() -> None:
    args = parse_args()

    if not docker_image_present():
        raise SystemExit(
            f"Required image is not present locally: {IMAGE}. Pull it before running the probe."
        )

    with tempfile.TemporaryDirectory(
        prefix="m12-hardened-boundary-",
    ) as temp_dir:
        root = Path(temp_dir)
        workspace = root / "workspace"
        outside = root / "outside"

        workspace.mkdir()
        os.chown(workspace, 65532, 65532)
        workspace.chmod(0o700)

        outside.mkdir()

        outside_read = outside / "read-sentinel.txt"
        outside_read.write_text(
            OUTSIDE_READ_MARKER,
            encoding="utf-8",
        )

        outside_write = outside / "write-sentinel.txt"

        symlink_escape = workspace / "m12-symlink-escape.txt"
        symlink_escape.symlink_to(outside_read)

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
        tcp_listener.bind(("127.0.0.1", 0))
        tcp_listener.listen(1)

        tcp_port = int(tcp_listener.getsockname()[1])

        try:
            probe = run_candidate_probe(
                workspace=workspace,
                outside_read=outside_read,
                outside_write=outside_write,
                unix_socket=unix_socket_path,
                tcp_port=tcp_port,
                timeout_seconds=args.probe_timeout_seconds,
            )

            (
                success_exit_observed,
                success_container_cleaned,
            ) = run_cleanup_probe(exit_code=0)

            (
                failure_exit_observed,
                failure_container_cleaned,
            ) = run_cleanup_probe(exit_code=7)

            (
                hard_timeout_enforced,
                timeout_container_cleaned,
            ) = run_timeout_probe(
                timeout_seconds=args.hard_timeout_seconds,
            )
        finally:
            tcp_listener.close()
            unix_listener.close()

        classification = classify(
            probe,
            success_exit_observed=success_exit_observed,
            success_container_cleaned=success_container_cleaned,
            failure_exit_observed=failure_exit_observed,
            failure_container_cleaned=failure_container_cleaned,
            hard_timeout_enforced=hard_timeout_enforced,
            timeout_container_cleaned=(timeout_container_cleaned),
        )

        artifact = {
            "suite_id": ("m12-hardened-container-boundary-v0"),
            "captured_at": datetime.now(UTC).isoformat(),
            "execution_host": "agent01",
            "container_engine": "docker",
            "container_engine_version": docker_version(),
            "image": IMAGE,
            "policy": {
                "network": "none",
                "read_only_rootfs": True,
                "cap_drop": "ALL",
                "no_new_privileges": True,
                "uid": 65532,
                "gid": 65532,
                "pids_limit": 64,
                "memory_limit_bytes": 256 * 1024 * 1024,
                "cpus": 1,
                "workspace_mount": "rw",
                "docker_socket_mounted": False,
            },
            "probe": {
                **probe,
                "success_exit_observed": success_exit_observed,
                "success_container_cleaned": success_container_cleaned,
                "failure_exit_observed": failure_exit_observed,
                "failure_container_cleaned": failure_container_cleaned,
                "hard_timeout_enforced": (hard_timeout_enforced),
                "timeout_container_cleaned": (timeout_container_cleaned),
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

    if args.output is not None:
        args.output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        args.output.write_text(
            serialized + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
