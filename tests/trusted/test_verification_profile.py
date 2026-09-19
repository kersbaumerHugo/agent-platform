from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from agent_platform.trust.verification_profile import (
    AuthoritativeVerificationProfile,
    VerificationCheck,
)


def test_m12_v0_profile_matches_authoritative_baseline() -> None:
    profile = AuthoritativeVerificationProfile()

    assert profile.version == "m12-v0"
    assert tuple(step.check for step in profile.steps) == (
        VerificationCheck.SYNTAX,
        VerificationCheck.RUFF_LINT,
        VerificationCheck.RUFF_FORMAT,
        VerificationCheck.TYPECHECK,
        VerificationCheck.TEST,
        VerificationCheck.PACKAGE,
        VerificationCheck.DIFF_CHECK,
    )

    assert tuple(step.argv for step in profile.steps) == (
        (
            "python",
            "-m",
            "compileall",
            "-q",
            "src",
            "tests",
            "scripts",
        ),
        (
            "python",
            "-m",
            "ruff",
            "check",
            "src",
            "tests",
            "scripts",
        ),
        (
            "python",
            "-m",
            "ruff",
            "format",
            "--check",
            "src",
            "tests",
            "scripts",
        ),
        (
            "python",
            "-m",
            "mypy",
            "src",
        ),
        (
            "python",
            "-m",
            "pytest",
            "-q",
        ),
        (
            "python",
            "-m",
            "build",
        ),
        (
            "git",
            "diff",
            "--check",
        ),
    )


def test_profile_cannot_be_relaxed_by_caller() -> None:
    with pytest.raises(TypeError):
        AuthoritativeVerificationProfile(steps=())  # type: ignore[call-arg]


def test_profile_is_frozen_after_construction() -> None:
    profile = AuthoritativeVerificationProfile()

    with pytest.raises(FrozenInstanceError):
        profile.version = "caller-controlled"  # type: ignore[misc]


def test_profile_steps_are_argv_not_shell_commands() -> None:
    profile = AuthoritativeVerificationProfile()

    for step in profile.steps:
        assert isinstance(step.argv, tuple)
        assert step.argv
        assert all(isinstance(part, str) and part for part in step.argv)
