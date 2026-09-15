import asyncio
import json
from pathlib import Path

import pytest

from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
)
from agent_platform.worker.publication import (
    TrustedPublicationClient,
)


@pytest.mark.asyncio
async def test_client_submits_change_set_and_reads_acceptance(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "publisher.sock"
    received: list[dict[str, object]] = []

    async def handler(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        raw = await reader.readline()
        received.append(json.loads(raw))

        writer.write(
            json.dumps(
                {
                    "status": "accepted",
                    "reference": ("https://github.com/kersbaumerHugo/agent-platform/pull/99"),
                }
            ).encode("utf-8")
            + b"\n"
        )

        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(
        handler,
        path=socket_path,
    )

    try:
        client = TrustedPublicationClient(
            socket_path=socket_path,
        )

        response = await client.publish(
            ChangeSet(
                base_revision="abc123",
                branch_name="agent/test",
                commit_message="test: publish",
                changes=(
                    FileChange(
                        path="docs/example.md",
                        operation=(FileChangeOperation.UPSERT),
                        content="hello\n",
                    ),
                ),
            )
        )
    finally:
        server.close()
        await server.wait_closed()

    assert response.status == "accepted"
    assert response.reference is not None

    assert len(received) == 1
    assert received[0]["version"] == 1
    assert received[0]["branch_name"] == "agent/test"


@pytest.mark.asyncio
async def test_client_reads_policy_rejection(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "publisher.sock"

    async def handler(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        await reader.readline()

        writer.write(
            json.dumps(
                {
                    "status": "rejected",
                    "reason_code": ("protected_path_modified"),
                    "blocked_paths": [".github/workflows/ci.yml"],
                }
            ).encode("utf-8")
            + b"\n"
        )

        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(
        handler,
        path=socket_path,
    )

    try:
        client = TrustedPublicationClient(
            socket_path=socket_path,
        )

        response = await client.publish(
            ChangeSet(
                base_revision="abc123",
                branch_name="agent/test",
                commit_message="test: rejected",
                changes=(
                    FileChange(
                        path=".github/workflows/ci.yml",
                        operation=(FileChangeOperation.UPSERT),
                        content="evil\n",
                    ),
                ),
            )
        )
    finally:
        server.close()
        await server.wait_closed()

    assert response.status == "rejected"
    assert response.reason_code == "protected_path_modified"
    assert response.blocked_paths == (".github/workflows/ci.yml",)
