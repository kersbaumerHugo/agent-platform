"""Pytest test for the self-development marker."""

from agent_platform.worker.self_development_marker import marker


def test_marker_returns_exact_string() -> None:
    """marker() must return exactly 'm6-self-development-e2e'."""
    assert marker() == "m6-self-development-e2e"