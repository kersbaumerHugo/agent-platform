from pathlib import Path
from uuid import uuid4

import pytest

from agent_platform.adapters.runtimes.dsh import DSHRuntime
from agent_platform.domain.models import RuntimeRequest


class FakeDSHResult:
    final_response = "hello from dsh"
    finish_reason = "completed"


class FakeDSHClient:
    def __init__(self) -> None:
        self.closed = False
        self.prompt: str | None = None
        self.session_id: str | None = None

    def run(
        self,
        prompt: str,
        *,
        session_id: str,
        on_notification=None,
    ) -> FakeDSHResult:
        self.prompt = prompt
        self.session_id = session_id

        if on_notification is not None:
            on_notification(
                type(
                    "Notification",
                    (),
                    {
                        "method": "session.status",
                        "payload": {
                            "status": "busy",
                        },
                    },
                )()
            )

        return FakeDSHResult()

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_dsh_runtime_maps_runtime_contract() -> None:
    client = FakeDSHClient()
    run_id = uuid4()

    runtime = DSHRuntime(
        dsh_home=Path(".runtime/dsh"),
        cwd=Path("."),
        provider="test-provider",
        model="test-model",
        client_factory=lambda: client,
    )

    result = await runtime.execute(
        RuntimeRequest(
            run_id=run_id,
            agent_id="demo",
            input="hello runtime",
        )
    )

    assert runtime.name == "dsh"
    assert result.output == "hello from dsh"

    assert client.prompt == "hello runtime"
    assert client.session_id == str(run_id)
    assert client.closed is False

    runtime.close()

    assert client.closed is True


@pytest.mark.asyncio
async def test_dsh_runtime_forwards_notifications() -> None:
    client = FakeDSHClient()
    received: list[object] = []

    runtime = DSHRuntime(
        dsh_home=Path(".runtime/dsh"),
        cwd=Path("."),
        provider="test-provider",
        model="test-model",
        client_factory=lambda: client,
        notification_callback=received.append,
    )

    await runtime.execute(
        RuntimeRequest(
            run_id=uuid4(),
            agent_id="demo",
            input="hello runtime",
        )
    )

    assert len(received) == 1

    notification = received[0]

    assert notification.method == ("session.status")

    assert notification.payload == {
        "status": "busy",
    }


@pytest.mark.asyncio
async def test_dsh_runtime_reuses_client_across_runs() -> None:
    client = FakeDSHClient()
    factory_calls = 0

    def client_factory() -> FakeDSHClient:
        nonlocal factory_calls
        factory_calls += 1
        return client

    runtime = DSHRuntime(
        dsh_home=Path(".runtime/dsh"),
        cwd=Path("."),
        provider="test-provider",
        model="test-model",
        client_factory=client_factory,
    )

    first_run_id = uuid4()
    second_run_id = uuid4()

    first = await runtime.execute(
        RuntimeRequest(
            run_id=first_run_id,
            agent_id="demo",
            input="initial implementation",
        )
    )

    second = await runtime.execute(
        RuntimeRequest(
            run_id=second_run_id,
            agent_id="demo",
            input="repair implementation",
        )
    )

    assert first.output == "hello from dsh"
    assert second.output == "hello from dsh"

    assert factory_calls == 1
    assert client.prompt == "repair implementation"
    assert client.session_id == str(second_run_id)
    assert client.closed is False

    runtime.close()

    assert client.closed is True


def test_dsh_runtime_close_is_idempotent() -> None:
    client = FakeDSHClient()

    runtime = DSHRuntime(
        dsh_home=Path(".runtime/dsh"),
        cwd=Path("."),
        provider="test-provider",
        model="test-model",
        client_factory=lambda: client,
    )

    runtime.close()
    runtime.close()

    assert client.closed is False
