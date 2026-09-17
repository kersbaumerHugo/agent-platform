import json

import pytest

from scripts.run_context_aware_execution_smoke import (
    RAW_CONTEXT_MARKER,
    execute_smoke,
)


@pytest.mark.asyncio
async def test_m11_smoke_runs_context_aware_work_end_to_end(
    tmp_path,
) -> None:
    report = await execute_smoke(tmp_path / "memory.sqlite3")

    work = report["context_aware_work"]

    assert work["status"] == "succeeded"
    assert [step["step_id"] for step in work["steps"]] == ["draft", "review"]
    assert all(step["context_trace"] is not None for step in work["steps"])
    assert all(
        observation["binding_present"] for observation in report["context_runtime_observations"]
    )
    assert all(
        observation["context_message_count"] == 1
        for observation in report["context_runtime_observations"]
    )
    assert report["all_bindings_cleared"] is True


@pytest.mark.asyncio
async def test_m11_smoke_preserves_context_free_execution(
    tmp_path,
) -> None:
    report = await execute_smoke(tmp_path / "memory.sqlite3")

    work = report["no_context_work"]
    observation = work["runtime_observations"][0]

    assert work["status"] == "succeeded"
    assert work["steps"][0]["context_trace"] is None
    assert observation["binding_present"] is False
    assert observation["binding_required"] is False
    assert observation["context_message_count"] == 0
    assert observation["message_roles"] == [
        "system",
        "user",
    ]


@pytest.mark.asyncio
async def test_m11_smoke_artifact_excludes_raw_context(
    tmp_path,
) -> None:
    report = await execute_smoke(tmp_path / "memory.sqlite3")

    serialized = json.dumps(
        report,
        sort_keys=True,
    )

    assert report["raw_context_absent"] is True
    assert RAW_CONTEXT_MARKER not in serialized


@pytest.mark.asyncio
async def test_m11_smoke_is_deterministic_across_fresh_databases(
    tmp_path,
) -> None:
    first = await execute_smoke(tmp_path / "first.sqlite3")
    second = await execute_smoke(tmp_path / "second.sqlite3")

    assert first == second
