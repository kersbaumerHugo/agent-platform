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
