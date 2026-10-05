import pytest

from agent_platform.application.model_routing import (
    ModelRoute,
    ModelRoutingPolicy,
)


def test_resolves_semantic_route_to_model() -> None:
    policy = ModelRoutingPolicy(
        routes=(
            ModelRoute(
                route="local_small",
                model="local-small-model",
            ),
            ModelRoute(
                route="local_strong",
                model="local-strong-model",
            ),
            ModelRoute(
                route="remote_strong",
                model="remote-strong-model",
            ),
        )
    )

    assert policy.resolve("local_small") == "local-small-model"
    assert policy.resolve("remote_strong") == "remote-strong-model"


def test_rejects_unknown_route() -> None:
    policy = ModelRoutingPolicy(
        routes=(
            ModelRoute(
                route="local_small",
                model="local-small-model",
            ),
        )
    )

    with pytest.raises(
        ValueError,
        match="No model configured",
    ):
        policy.resolve("remote_strong")
