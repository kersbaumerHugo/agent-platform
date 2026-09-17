from pathlib import Path

import pytest

from agent_platform.adapters.runtimes.dsh import DSHRuntime
from agent_platform.adapters.runtimes.fake import FakeRuntime
from agent_platform.api.composition import build_runtime


def test_runtime_defaults_to_fake() -> None:
    runtime = build_runtime({})

    assert isinstance(runtime, FakeRuntime)
    assert runtime.name == "fake"


def test_runtime_explicit_fake() -> None:
    runtime = build_runtime(
        {
            "AGENT_PLATFORM_RUNTIME": "fake",
        }
    )

    assert isinstance(runtime, FakeRuntime)


def test_runtime_builds_dsh_from_configuration() -> None:
    runtime = build_runtime(
        {
            "AGENT_PLATFORM_RUNTIME": "dsh",
            "AGENT_PLATFORM_DSH_PROVIDER": "test-provider",
            "AGENT_PLATFORM_DSH_MODEL": "test-model",
            "AGENT_PLATFORM_DSH_HOME": ".runtime/test-dsh",
            "AGENT_PLATFORM_DSH_CWD": ".",
            "AGENT_PLATFORM_DSH_PROFILE": "sdk",
            "AGENT_PLATFORM_DSH_TIMEOUT_SECONDS": "45",
            "AGENT_PLATFORM_DSH_PATCHES": (
                "config/dsh/platform-mcp.cordis.yml,config/dsh/second.cordis.yml"
            ),
        }
    )

    assert isinstance(runtime, DSHRuntime)
    assert runtime.name == "dsh"
    assert runtime._dsh_home == Path(".runtime/test-dsh").resolve()
    assert runtime._cwd == Path(".").resolve()
    assert runtime._provider == "test-provider"
    assert runtime._model == "test-model"
    assert runtime._profile == "sdk"
    assert runtime._request_timeout_seconds == 45.0
    assert runtime._patches == (
        Path("config/dsh/platform-mcp.cordis.yml").resolve(),
        Path("config/dsh/second.cordis.yml").resolve(),
    )


@pytest.mark.parametrize(
    "missing",
    (
        "AGENT_PLATFORM_DSH_PROVIDER",
        "AGENT_PLATFORM_DSH_MODEL",
    ),
)
def test_dsh_requires_provider_and_model(
    missing: str,
) -> None:
    env = {
        "AGENT_PLATFORM_RUNTIME": "dsh",
        "AGENT_PLATFORM_DSH_PROVIDER": "test-provider",
        "AGENT_PLATFORM_DSH_MODEL": "test-model",
    }
    del env[missing]

    with pytest.raises(
        ValueError,
        match=missing,
    ):
        build_runtime(env)


@pytest.mark.parametrize(
    "timeout",
    (
        "invalid",
        "0",
        "-1",
    ),
)
def test_dsh_rejects_invalid_timeout(
    timeout: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="AGENT_PLATFORM_DSH_TIMEOUT_SECONDS",
    ):
        build_runtime(
            {
                "AGENT_PLATFORM_RUNTIME": "dsh",
                "AGENT_PLATFORM_DSH_PROVIDER": "test-provider",
                "AGENT_PLATFORM_DSH_MODEL": "test-model",
                "AGENT_PLATFORM_DSH_TIMEOUT_SECONDS": timeout,
            }
        )


def test_unknown_runtime_fails_closed() -> None:
    with pytest.raises(
        ValueError,
        match="Unsupported AGENT_PLATFORM_RUNTIME",
    ):
        build_runtime(
            {
                "AGENT_PLATFORM_RUNTIME": "mystery",
            }
        )
