import pytest

from agent_platform.adapters.observability.prometheus import PrometheusObserver
from agent_platform.adapters.runtimes.fake import FakeRuntime
from agent_platform.application.run_agent import RunAgent
from agent_platform.domain.models import RunRequest, RunStatus


@pytest.mark.asyncio
async def test_run_agent_uses_runtime_contract():
    service = RunAgent(FakeRuntime(), PrometheusObserver())

    result = await service.execute(
        RunRequest(agent_id="demo", input="hello")
    )

    assert result.status == RunStatus.SUCCEEDED
    assert result.run_id is not None
    assert "[fake-runtime]" in (result.output or "")
