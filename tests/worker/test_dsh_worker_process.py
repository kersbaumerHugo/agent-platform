import os
import subprocess
import sys
from pathlib import Path


def test_dsh_process_rejects_missing_configuration(
    tmp_path: Path,
) -> None:
    env = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": os.environ.get(
            "PYTHONPATH",
            "",
        ),
    }

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_platform.worker.dsh_process",
        ],
        cwd=tmp_path,
        input="implement something\n",
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=5,
    )

    assert result.returncode == 1

    assert "AGENT_PLATFORM_DSH_HOME" in result.stderr


def test_dsh_process_rejects_empty_goal(
    tmp_path: Path,
) -> None:
    env = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": os.environ.get(
            "PYTHONPATH",
            "",
        ),
    }

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_platform.worker.dsh_process",
        ],
        cwd=tmp_path,
        input="",
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=5,
    )

    assert result.returncode == 1
    assert "empty goal" in result.stderr


def test_lifecycle_observer_emits_only_safe_metadata(
    capsys,
) -> None:
    from types import SimpleNamespace

    from agent_platform.worker.dsh_process import (
        _lifecycle_observer,
    )

    observer = _lifecycle_observer()

    observer(
        SimpleNamespace(
            method="session.event",
            payload={
                "secret": "must-not-leak",
                "event": {
                    "type": "tool/call",
                    "data": {
                        "arguments": "also-secret",
                    },
                },
            },
        )
    )

    captured = capsys.readouterr()

    assert "DSH_LIFECYCLE" in captured.err
    assert '"method": "session.event"' in captured.err
    assert '"event_type": "tool/call"' in captured.err

    assert "must-not-leak" not in captured.err
    assert "also-secret" not in captured.err
