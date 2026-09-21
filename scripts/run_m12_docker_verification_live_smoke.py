from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from agent_platform.trust.authoritative_verifier import AuthoritativeVerifier
from agent_platform.trust.verification import VerificationOutcome
from agent_platform.trust.verification_docker import (
    DockerVerificationConfig,
    DockerVerificationProcessRunner,
)
from agent_platform.trust.verification_executor import (
    ProfileVerificationExecutor,
    VerificationProcessOutcome,
)

_FIXTURE_PATH = Path("src/agent_platform/application/m12_verifier_live_fixture.py")
_FIXTURE_CONTENT = 'MESSAGE = "m12.6 hardened verifier live smoke"\n'


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ["PATH"],
            "HOME": "/tmp",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C.UTF-8",
        },
    )

    if result.returncode != 0:
        raise RuntimeError("Git command failed during verifier live smoke.")

    return result.stdout.strip()


def _copy_project(source: Path, workspace: Path) -> None:
    required = (
        "pyproject.toml",
        "src",
        "tests",
        "scripts",
    )

    for name in required:
        target = source / name
        if not target.exists():
            raise RuntimeError(f"Required project path is missing: {name}")

    for name in ("pyproject.toml", ".gitignore"):
        source_file = source / name
        if source_file.exists():
            shutil.copy2(
                source_file,
                workspace / name,
            )

    for name in ("src", "tests", "scripts"):
        shutil.copytree(
            source / name,
            workspace / name,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
            ),
        )


def _prepare_workspace(
    source: Path,
    root: Path,
) -> tuple[Path, str]:
    workspace = root / "workspace"
    workspace.mkdir()

    _copy_project(source, workspace)

    _git(workspace, "init", "-b", "main")
    _git(workspace, "add", "-A")
    _git(
        workspace,
        "-c",
        "user.name=Agent Platform Verifier Smoke",
        "-c",
        "user.email=verifier-smoke@example.invalid",
        "commit",
        "-m",
        "chore: establish verifier smoke baseline",
    )

    base_revision = _git(
        workspace,
        "rev-parse",
        "HEAD",
    )

    fixture = workspace / _FIXTURE_PATH
    fixture.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    fixture.write_text(
        _FIXTURE_CONTENT,
        encoding="utf-8",
    )

    return workspace, base_revision


async def _probe(
    runner: DockerVerificationProcessRunner,
    *,
    workspace: Path,
    code: str,
) -> bool:
    result = await runner.run(
        workspace=workspace,
        argv=(
            "python",
            "-c",
            code,
        ),
    )

    return result.outcome is VerificationProcessOutcome.EXITED and result.exit_code == 0


async def _run(
    *,
    image: str,
) -> int:
    source = Path.cwd().resolve()

    with tempfile.TemporaryDirectory(
        prefix="m12-6-verifier-live-",
    ) as raw_root:
        root = Path(raw_root)
        workspace, base_revision = _prepare_workspace(
            source,
            root,
        )
        runtime_root = root / "runtime"
        runtime_root.mkdir()

        runner = DockerVerificationProcessRunner(
            config=DockerVerificationConfig(
                image=image,
                runtime_root=runtime_root,
                hard_timeout_seconds=300.0,
                terminate_grace_seconds=5.0,
                pids_limit=128,
                memory_limit="1g",
                cpu_limit="2",
                tmpfs_spec="/tmp:rw,exec,nosuid,nodev,size=256m",
            )
        )

        probes = {
            "network_none": await _probe(
                runner,
                workspace=workspace,
                code=(
                    "import socket,sys;"
                    "s=socket.socket();s.settimeout(1);"
                    "\ntry:s.connect(('1.1.1.1',53));sys.exit(1)"
                    "\nexcept OSError:sys.exit(0)"
                ),
            ),
            "rootfs_read_only": await _probe(
                runner,
                workspace=workspace,
                code=(
                    "import pathlib,sys;"
                    "\ntry:pathlib.Path('/etc/m12-probe').write_text('x');sys.exit(1)"
                    "\nexcept OSError:sys.exit(0)"
                ),
            ),
            "workspace_write_allowed": await _probe(
                runner,
                workspace=workspace,
                code=(
                    "import pathlib;"
                    "p=pathlib.Path('m12-boundary-probe.tmp');"
                    "p.write_text('ok');p.unlink()"
                ),
            ),
            "git_metadata_read_only": await _probe(
                runner,
                workspace=workspace,
                code=(
                    "import pathlib,sys;"
                    "\ntry:pathlib.Path('.git/m12-probe').write_text('x');sys.exit(1)"
                    "\nexcept OSError:sys.exit(0)"
                ),
            ),
            "authority_sockets_absent": await _probe(
                runner,
                workspace=workspace,
                code=(
                    "import pathlib,sys;"
                    "paths=['/var/run/docker.sock',"
                    "'/run/docker.sock',"
                    "'/run/agent-platform/trusted-change.sock'];"
                    "sys.exit(0 if not any(pathlib.Path(p).exists() for p in paths) else 1)"
                ),
            ),
            "no_new_privileges_and_zero_effective_caps": await _probe(
                runner,
                workspace=workspace,
                code=(
                    "import pathlib,sys;"
                    "text=pathlib.Path('/proc/self/status').read_text();"
                    "values=dict("
                    "line.split(':',1) for line in text.splitlines() if ':' in line"
                    ");"
                    "ok=values.get('NoNewPrivs','').strip()=='1' and "
                    "int(values.get('CapEff','0').strip(),16)==0;"
                    "sys.exit(0 if ok else 1)"
                ),
            ),
        }

        executor = ProfileVerificationExecutor(
            runner=runner,
        )
        verifier = AuthoritativeVerifier(
            executor=executor,
        )
        result = await verifier.verify(
            workspace=workspace,
        )

        fixture = workspace / _FIXTURE_PATH
        final_head = _git(
            workspace,
            "rev-parse",
            "HEAD",
        )
        changed_paths = tuple(
            path
            for path in _git(
                workspace,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ).splitlines()
            if path
        )

        checks = {
            **probes,
            "authoritative_profile_passed": (result.outcome is VerificationOutcome.PASS),
            "authoritative_checks_complete": (
                len(result.steps) == 7
                and all(step.outcome is VerificationOutcome.PASS for step in result.steps)
            ),
            "git_head_unchanged": (final_head == base_revision),
            "fixture_content_unchanged": (fixture.read_text(encoding="utf-8") == _FIXTURE_CONTENT),
            "fixture_remains_uncommitted": any(
                entry.endswith(str(_FIXTURE_PATH)) for entry in changed_paths
            ),
        }

        accepted = all(checks.values())

        payload = {
            "candidate_accepted": accepted,
            "decision": (
                "hardened_authoritative_verifier_boundary_pass"
                if accepted
                else "hardened_authoritative_verifier_boundary_failed"
            ),
            "image": image,
            "profile_version": result.profile_version,
            "profile_outcome": result.outcome.value,
            "checks": checks,
        }

        print(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
            )
        )

        return 0 if accepted else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the M12.6 hardened verifier live smoke.",
    )
    parser.add_argument(
        "--image",
        required=True,
        help="Exact verifier image ID, for example sha256:<64 hex chars>.",
    )
    args = parser.parse_args()

    return asyncio.run(
        _run(
            image=args.image,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
