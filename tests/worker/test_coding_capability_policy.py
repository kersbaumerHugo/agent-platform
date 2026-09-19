from dataclasses import FrozenInstanceError

import pytest

from agent_platform.worker.capability import (
    CodingCapability,
    CodingCapabilityPolicy,
    ForbiddenCodingAuthority,
)


def test_m12_v0_policy_grants_only_required_coding_capabilities() -> None:
    policy = CodingCapabilityPolicy()

    assert policy.version == "m12-v0"

    assert policy.allowed == (
        CodingCapability.WORKSPACE_READ,
        CodingCapability.WORKSPACE_WRITE,
        CodingCapability.PROCESS_EXECUTION,
        CodingCapability.MODEL_GATEWAY_REQUEST,
    )

    assert all(policy.allows(capability) for capability in policy.allowed)


def test_m12_v0_policy_denies_trusted_and_unrestricted_authorities() -> None:
    policy = CodingCapabilityPolicy()

    assert policy.denied == (
        ForbiddenCodingAuthority.HOST_FILESYSTEM,
        ForbiddenCodingAuthority.PUBLISHER_SOCKET,
        ForbiddenCodingAuthority.DOCKER_SOCKET,
        ForbiddenCodingAuthority.DIRECT_LAN,
        ForbiddenCodingAuthority.INTERNET_EGRESS,
        ForbiddenCodingAuthority.PUBLICATION_CREDENTIAL,
        ForbiddenCodingAuthority.GIT_PUSH,
        ForbiddenCodingAuthority.MERGE,
        ForbiddenCodingAuthority.PRIVILEGE_ESCALATION,
    )

    assert all(policy.denies(authority) for authority in policy.denied)


def test_m12_v0_policy_cannot_be_relaxed_by_construction() -> None:
    with pytest.raises(TypeError):
        CodingCapabilityPolicy(  # type: ignore[call-arg]
            allowed=(CodingCapability.WORKSPACE_READ,)
        )


def test_m12_v0_policy_is_immutable() -> None:
    policy = CodingCapabilityPolicy()

    with pytest.raises(FrozenInstanceError):
        policy.version = "relaxed"  # type: ignore[misc]
