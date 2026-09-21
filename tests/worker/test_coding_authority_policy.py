from dataclasses import FrozenInstanceError

import pytest

from agent_platform.worker.authority import (
    CodingAuthority,
    CodingAuthorityPolicy,
    ForbiddenCodingAuthority,
)


def test_m12_v0_policy_grants_only_required_coding_capabilities() -> None:
    policy = CodingAuthorityPolicy()

    assert policy.version == "m12-v0"

    assert policy.allowed == (
        CodingAuthority.WORKSPACE_READ,
        CodingAuthority.WORKSPACE_WRITE,
        CodingAuthority.PROCESS_EXECUTION,
        CodingAuthority.MODEL_GATEWAY_REQUEST,
    )

    assert all(policy.allows(capability) for capability in policy.allowed)


def test_m12_v0_policy_denies_trusted_and_unrestricted_authorities() -> None:
    policy = CodingAuthorityPolicy()

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
        CodingAuthorityPolicy(  # type: ignore[call-arg]
            allowed=(CodingAuthority.WORKSPACE_READ,)
        )


def test_m12_v0_policy_is_immutable() -> None:
    policy = CodingAuthorityPolicy()

    with pytest.raises(FrozenInstanceError):
        policy.version = "relaxed"  # type: ignore[misc]
