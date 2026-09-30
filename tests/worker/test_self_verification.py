from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.worker.self_verification import (
    WorkerSelfVerificationResult,
    build_self_repair_goal,
    run_worker_self_verification,
)


@pytest.mark.asyncio
async def test_self_verification_passes_for_green_pytest(
    tmp_path: Path,
) -> None:
    (tmp_path / "test_example.py").write_text(
        "def test_example() -> None:\n    assert True\n",
        encoding="utf-8",
    )

    result = await run_worker_self_verification(tmp_path)

    assert result.passed
    assert result.exit_code == 0
    assert not result.timed_out


@pytest.mark.asyncio
async def test_self_verification_captures_failing_pytest(
    tmp_path: Path,
) -> None:
    (tmp_path / "test_example.py").write_text(
        "def test_example() -> None:\n    assert False\n",
        encoding="utf-8",
    )

    result = await run_worker_self_verification(tmp_path)

    assert not result.passed
    assert result.exit_code != 0
    assert "FAILED" in result.output


def test_repair_goal_contains_real_verification_evidence() -> None:
    verification = WorkerSelfVerificationResult(
        command=("python", "-m", "pytest", "-q"),
        exit_code=1,
        output="3 failed in 0.36s",
    )

    goal = build_self_repair_goal(
        original_goal="Implement the focused regression.",
        verification=verification,
    )

    assert "single bounded self-repair attempt" in goal
    assert "python -m pytest -q" in goal
    assert "exit_code: 1" in goal
    assert "3 failed in 0.36s" in goal
    assert "Do not weaken or delete tests" in goal


def test_phase_limited_repair_goal_explains_incomplete_attempt() -> None:
    verification = WorkerSelfVerificationResult(
        command=("python", "-m", "pytest", "-q"),
        exit_code=0,
        output="693 passed",
    )

    goal = build_self_repair_goal(
        original_goal="Implement the focused change.",
        verification=verification,
        phase_limited=True,
    )

    assert "phase limit before completing" in goal
    assert "single bounded self-repair attempt" in goal
    assert "693 passed" in goal
