import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agent_platform.trust.change_policy import (
    ChangePolicy,
)
from agent_platform.trust.change_request import (
    serialize_change_set,
)
from agent_platform.trust.publisher import (
    ChangeSet,
    FileChange,
    FileChangeOperation,
    PublicationResult,
    TrustedPublisher,
)
from agent_platform.trust.service import (
    TrustedChangeHandler,
    UnixSocketChangeServer,
)


@dataclass
class FakeSink:
    published: list[ChangeSet] = field(default_factory=list)

    async def publish(
        self,
        change_set: ChangeSet,
    ) -> PublicationResult:
        self.published.append(change_set)

        return PublicationResult(reference="fake://publication/1")


def make_change_set(
    path: str = "src/example.py",
) -> ChangeSet:
    return ChangeSet(
        base_revision="abc123",
        branch_name="agent/example",
        commit_message="feat: example",
        changes=(
            FileChange(
                path=path,
                operation=FileChangeOperation.UPSERT,
                content="VALUE = 42\n",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_handler_accepts_allowed_change() -> None:
    sink = FakeSink()

    handler = TrustedChangeHandler(
        TrustedPublisher(
            policy=ChangePolicy(),
            sink=sink,
        )
    )

    response = await handler.handle(serialize_change_set(make_change_set()))

    assert response.status == "accepted"
    assert response.reference == "fake://publication/1"
    assert len(sink.published) == 1


@pytest.mark.asyncio
async def test_handler_rejects_protected_change() -> None:
    sink = FakeSink()

    handler = TrustedChangeHandler(
        TrustedPublisher(
            policy=ChangePolicy(),
            sink=sink,
        )
    )

    response = await handler.handle(
        serialize_change_set(make_change_set(".github/workflows/ci.yml"))
    )

    assert response.status == "rejected"
    assert response.reason_code == "protected_path_modified"
    assert response.blocked_paths == (".github/workflows/ci.yml",)
    assert sink.published == []


@pytest.mark.asyncio
async def test_handler_fails_closed_on_invalid_request() -> None:
    sink = FakeSink()

    handler = TrustedChangeHandler(
        TrustedPublisher(
            policy=ChangePolicy(),
            sink=sink,
        )
    )

    response = await handler.handle('{"admin":true}')

    assert response.status == "error"
    assert response.error_code == "invalid_change_request"
    assert sink.published == []


@pytest.mark.asyncio
async def test_unix_socket_round_trip(
    tmp_path: Path,
) -> None:
    sink = FakeSink()

    socket_path = tmp_path / "trusted-change.sock"

    server = UnixSocketChangeServer(
        socket_path=socket_path,
        handler=TrustedChangeHandler(
            TrustedPublisher(
                policy=ChangePolicy(),
                sink=sink,
            )
        ),
    )

    await server.start()

    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)

        request = serialize_change_set(make_change_set())

        writer.write(request.encode("utf-8") + b"\n")
        await writer.drain()

        response_raw = await reader.readline()

        writer.close()
        await writer.wait_closed()

        response = json.loads(response_raw)

        assert response["status"] == "accepted"
        assert response["reference"] == ("fake://publication/1")
        assert len(sink.published) == 1
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_protected_change_over_socket_never_reaches_sink(
    tmp_path: Path,
) -> None:
    sink = FakeSink()

    socket_path = tmp_path / "trusted-change.sock"

    server = UnixSocketChangeServer(
        socket_path=socket_path,
        handler=TrustedChangeHandler(
            TrustedPublisher(
                policy=ChangePolicy(),
                sink=sink,
            )
        ),
    )

    await server.start()

    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)

        request = serialize_change_set(make_change_set("tests/trusted/test_change_policy.py"))

        writer.write(request.encode("utf-8") + b"\n")
        await writer.drain()

        response = json.loads(await reader.readline())

        writer.close()
        await writer.wait_closed()

        assert response["status"] == "rejected"
        assert sink.published == []
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_server_rejects_non_utf8_request(
    tmp_path: Path,
) -> None:
    sink = FakeSink()

    socket_path = tmp_path / "trusted-change.sock"

    server = UnixSocketChangeServer(
        socket_path=socket_path,
        handler=TrustedChangeHandler(
            TrustedPublisher(
                policy=ChangePolicy(),
                sink=sink,
            )
        ),
    )

    await server.start()

    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)

        writer.write(b"\xff\xfe\n")
        await writer.drain()

        response = json.loads(await reader.readline())

        writer.close()
        await writer.wait_closed()

        assert response == {
            "error_code": "invalid_encoding",
            "status": "error",
        }
        assert sink.published == []
    finally:
        await server.close()
