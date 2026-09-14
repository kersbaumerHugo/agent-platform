import pytest

from agent_platform.trust.change_policy import ChangePolicy


@pytest.fixture
def policy() -> ChangePolicy:
    return ChangePolicy()


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        "pyproject.toml",
        "pytest.ini",
        "tests/conftest.py",
        "src/agent_platform/trust/change_policy.py",
        "src/agent_platform/adapters/git/local.py",
        "tests/trusted/test_change_policy.py",
    ],
)
def test_rejects_protected_paths(
    policy: ChangePolicy,
    path: str,
) -> None:
    decision = policy.evaluate([path])

    assert decision.allowed is False
    assert path in decision.blocked_paths
    assert decision.reason_code == "protected_path_modified"


@pytest.mark.parametrize(
    "path",
    [
        "src/agent_platform/application/model_gateway.py",
        "src/agent_platform/adapters/models/openrouter.py",
        "tests/test_model_gateway.py",
        "docs/architecture.md",
    ],
)
def test_allows_normal_platform_changes(
    policy: ChangePolicy,
    path: str,
) -> None:
    decision = policy.evaluate([path])

    assert decision.allowed is True
    assert decision.blocked_paths == ()
    assert decision.reason_code == "allowed"


@pytest.mark.parametrize(
    "path",
    [
        "../ci.yml",
        "/etc/passwd",
        "",
        "   ",
    ],
)
def test_rejects_invalid_paths(
    policy: ChangePolicy,
    path: str,
) -> None:
    with pytest.raises(ValueError):
        policy.evaluate([path])


def test_rejects_entire_change_if_one_path_is_protected(
    policy: ChangePolicy,
) -> None:
    decision = policy.evaluate(
        [
            "src/agent_platform/application/model_gateway.py",
            ".github/workflows/ci.yml",
        ]
    )

    assert decision.allowed is False
    assert decision.blocked_paths == (".github/workflows/ci.yml",)
