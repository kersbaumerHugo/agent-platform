from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from uuid import UUID

from agent_platform.trust.docker_sandbox import (
    DockerSandboxBackend,
    DockerSandboxConfig,
)
from agent_platform.trust.sandbox_execution import (
    SandboxExecutionRequest,
)

EXECUTION_ID = UUID("dd2ce4b6-faf6-4b78-956a-88b6c4a06124")

SANDBOX_UID = 65532
SANDBOX_GID = 65532

BASE = Path("/run/m12-docker-backend-smoke")
WORKSPACE = BASE / "workspace"
RUNTIME = BASE / "runtime"


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()

    if not value:
        raise RuntimeError(f"{name} is required.")

    return value


CONTAINER_PROBE = r"""
import json
import os
import socket
from pathlib import Path


def tcp_reachable(host: str, port: int) -> bool:
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )
    sock.settimeout(1)

    try:
        sock.connect((host, port))
    except OSError:
        return False
    else:
        return True
    finally:
        sock.close()


def rootfs_write_allowed() -> bool:
    path = Path("/m12-rootfs-probe")

    try:
        path.write_text(
            "forbidden",
            encoding="utf-8",
        )
    except OSError:
        return False
    else:
        try:
            path.unlink()
        except OSError:
            pass
        return True


def gateway_auth_passed() -> bool:
    socket_path = os.environ[
        "AGENT_PLATFORM_GATEWAY_SOCKET"
    ]

    body = (
        b'{"model":"capability-probe",'
        b'"stream":false,'
        b'"messages":[{"role":"user",'
        b'"content":"probe"}]}'
    )

    request = (
        b"POST /internal/v1/chat/completions "
        b"HTTP/1.1\r\n"
        b"Host: gateway\r\n"
        b"Authorization: Bearer "
        b"sandbox-relay-placeholder\r\n"
        b"Content-Type: application/json\r\n"
        + (
            f"Content-Length: {len(body)}\r\n"
        ).encode()
        + b"Connection: close\r\n"
        + b"\r\n"
        + body
    )

    sock = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )
    sock.settimeout(10)

    try:
        sock.connect(socket_path)
        sock.sendall(request)

        chunks = []

        while True:
            chunk = sock.recv(65536)

            if not chunk:
                break

            chunks.append(chunk)
    finally:
        sock.close()

    response = b"".join(chunks)

    return (
        response.startswith(b"HTTP/1.1 400")
        and b"requires streaming" in response
    )


workspace_probe = Path(
    "/workspace/m12-write-probe.txt"
)
workspace_probe.write_text(
    "workspace write allowed\\n",
    encoding="utf-8",
)

status = Path(
    "/proc/self/status"
).read_text(
    encoding="utf-8"
)

cap_eff = next(
    line.split(":", 1)[1].strip()
    for line in status.splitlines()
    if line.startswith("CapEff:")
)

no_new_privileges = next(
    line.split(":", 1)[1].strip()
    for line in status.splitlines()
    if line.startswith("NoNewPrivs:")
)

result = {
    "cap_eff": cap_eff,
    "docker_socket_visible": Path(
        "/var/run/docker.sock"
    ).exists(),
    "gateway_auth_passed_via_uds": (
        gateway_auth_passed()
    ),
    "gateway_secret_is_placeholder": (
        os.environ.get("DEEPSEEK_API_KEY")
        == "sandbox-relay-placeholder"
    ),
    "gid": os.getgid(),
    "host_ssh_reachable": tcp_reachable(
        "172.17.0.1",
        22,
    ),
    "internet_reachable": tcp_reachable(
        "1.1.1.1",
        443,
    ),
    "no_new_privileges": (
        no_new_privileges == "1"
    ),
    "publisher_socket_visible": Path(
        "/run/agent-platform/"
        "trusted-change.sock"
    ).exists(),
    "rootfs_write_allowed": (
        rootfs_write_allowed()
    ),
    "uid": os.getuid(),
    "workspace_write_allowed": (
        workspace_probe.read_text(
            encoding="utf-8"
        )
        == "workspace write allowed\\n"
    ),
}

workspace_probe.unlink()

print(
    json.dumps(
        result,
        sort_keys=True,
    )
)
"""


def main() -> None:
    image = required_env("M12_SANDBOX_IMAGE")
    gateway_api_key = required_env("M12_MODEL_GATEWAY_API_KEY")

    if BASE.exists():
        shutil.rmtree(BASE)

    WORKSPACE.mkdir(
        parents=True,
        mode=0o700,
    )
    RUNTIME.mkdir(
        parents=True,
        mode=0o755,
    )

    os.chown(
        WORKSPACE,
        SANDBOX_UID,
        SANDBOX_GID,
    )

    config = DockerSandboxConfig(
        image=image,
        command=(
            "python",
            "-c",
            CONTAINER_PROBE,
        ),
        runtime_root=RUNTIME,
        gateway_upstream_host=("192.168.10.30"),
        gateway_upstream_port=8000,
        gateway_api_key=gateway_api_key,
        hard_timeout_seconds=30.0,
    )

    backend = DockerSandboxBackend(config=config)

    request = SandboxExecutionRequest(
        execution_id=EXECUTION_ID,
        workspace_name=WORKSPACE.name,
        goal="m12 live boundary probe",
    )

    try:
        outcome = asyncio.run(
            backend.execute(
                request,
                workspace=WORKSPACE,
            )
        )

        probe = json.loads(outcome.summary)

        expected = {
            "cap_eff": "0000000000000000",
            "docker_socket_visible": False,
            "gateway_auth_passed_via_uds": True,
            "gateway_secret_is_placeholder": True,
            "gid": SANDBOX_GID,
            "host_ssh_reachable": False,
            "internet_reachable": False,
            "no_new_privileges": True,
            "publisher_socket_visible": False,
            "rootfs_write_allowed": False,
            "uid": SANDBOX_UID,
            "workspace_write_allowed": True,
        }

        violations = {
            key: {
                "expected": expected[key],
                "actual": probe.get(key),
            }
            for key in expected
            if probe.get(key) != expected[key]
        }

        result = {
            "candidate_accepted": not violations,
            "decision": (
                "docker_backend_live_boundary_pass"
                if not violations
                else "docker_backend_live_boundary_fail"
            ),
            "probe": probe,
            "violations": violations,
        }

        print(
            json.dumps(
                result,
                indent=2,
                sort_keys=True,
            )
        )

        if violations:
            raise SystemExit(1)
    finally:
        shutil.rmtree(
            BASE,
            ignore_errors=True,
        )


if __name__ == "__main__":
    main()
