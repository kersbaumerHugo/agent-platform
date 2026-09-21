import pytest

from agent_platform.adapters.models.local_openai import (
    LocalOpenAIModelAdapter,
)
from agent_platform.adapters.models.openrouter import (
    OpenRouterModelAdapter,
)
from agent_platform.api.composition import build_model_gateway
from agent_platform.domain.observability import ObservationEvent


class NoopObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        del event


def test_model_gateway_defaults_to_openrouter() -> None:
    gateway = build_model_gateway(
        {
            "OPENROUTER_API_KEY": "test-key",
        },
        observer=NoopObserver(),
    )

    assert isinstance(
        gateway._model,
        OpenRouterModelAdapter,
    )
    assert gateway._model.provider == "openrouter"
    assert gateway._model.model == "openrouter/free"


def test_model_gateway_builds_configured_openrouter() -> None:
    gateway = build_model_gateway(
        {
            "MODEL_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_MODEL": "test/model",
        },
        observer=NoopObserver(),
    )

    assert isinstance(
        gateway._model,
        OpenRouterModelAdapter,
    )
    assert gateway._model.model == "test/model"


def test_model_gateway_builds_local_provider() -> None:
    gateway = build_model_gateway(
        {
            "MODEL_PROVIDER": "local",
            "LOCAL_MODEL_API_KEY": "local-key",
            "LOCAL_MODEL_BASE_URL": ("http://127.0.0.1:11434/v1"),
            "LOCAL_MODEL_NAME": "local-model",
        },
        observer=NoopObserver(),
    )

    assert isinstance(
        gateway._model,
        LocalOpenAIModelAdapter,
    )
    assert gateway._model.provider == "local"
    assert gateway._model.model == "local-model"


def test_openrouter_requires_api_key() -> None:
    with pytest.raises(
        ValueError,
        match="OPENROUTER_API_KEY",
    ):
        build_model_gateway(
            {},
            observer=NoopObserver(),
        )


@pytest.mark.parametrize(
    "missing",
    (
        "LOCAL_MODEL_API_KEY",
        "LOCAL_MODEL_BASE_URL",
        "LOCAL_MODEL_NAME",
    ),
)
def test_local_provider_requires_configuration(
    missing: str,
) -> None:
    env = {
        "MODEL_PROVIDER": "local",
        "LOCAL_MODEL_API_KEY": "local-key",
        "LOCAL_MODEL_BASE_URL": ("http://127.0.0.1:11434/v1"),
        "LOCAL_MODEL_NAME": "local-model",
    }

    del env[missing]

    with pytest.raises(
        ValueError,
        match=missing,
    ):
        build_model_gateway(
            env,
            observer=NoopObserver(),
        )


def test_unknown_model_provider_fails_closed() -> None:
    with pytest.raises(
        ValueError,
        match="Unsupported MODEL_PROVIDER",
    ):
        build_model_gateway(
            {
                "MODEL_PROVIDER": "mystery",
            },
            observer=NoopObserver(),
        )
