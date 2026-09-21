import pytest

from agent_platform.application.capability_authorization import (
    StaticCapabilityAuthorizationPolicy,
)
from agent_platform.contracts.authorization import (
    CapabilityAuthorizationContract,
)
from agent_platform.domain.capability import CapabilityDefinition

CODING = CapabilityDefinition(
    name="coding.execute",
    description="Execute supervised coding.",
)

REPOSITORY_INSPECT = CapabilityDefinition(
    name="repository.inspect",
    description="Inspect repository information.",
)


def test_exact_grant_allows_capability() -> None:
    policy: CapabilityAuthorizationContract = StaticCapabilityAuthorizationPolicy(
        grants=[
            (
                "agent:developer",
                "coding.execute",
            )
        ]
    )

    decision = policy.authorize(
        principal_id="agent:developer",
        capability=CODING,
    )

    assert decision.allowed is True
    assert decision.reason_code == "allowed"
    assert decision.policy_version == "m13-v0"


def test_missing_principal_is_denied() -> None:
    policy = StaticCapabilityAuthorizationPolicy()

    decision = policy.authorize(
        principal_id=None,
        capability=CODING,
    )

    assert decision.allowed is False
    assert decision.reason_code == "missing_principal"


def test_ungranted_principal_is_denied() -> None:
    policy = StaticCapabilityAuthorizationPolicy()

    decision = policy.authorize(
        principal_id="mcp:anonymous",
        capability=CODING,
    )

    assert decision.allowed is False
    assert decision.reason_code == "capability_not_granted"


def test_grant_does_not_authorize_different_capability() -> None:
    policy = StaticCapabilityAuthorizationPolicy(
        grants=[
            (
                "agent:developer",
                "repository.inspect",
            )
        ]
    )

    decision = policy.authorize(
        principal_id="agent:developer",
        capability=CODING,
    )

    assert decision.allowed is False
    assert decision.reason_code == "capability_not_granted"


def test_invalid_grant_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="principal must not be blank",
    ):
        StaticCapabilityAuthorizationPolicy(
            grants=[
                (
                    " ",
                    "coding.execute",
                )
            ]
        )
