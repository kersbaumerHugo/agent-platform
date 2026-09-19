from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agent_platform.trust.authoritative_verifier import AuthoritativeVerifier
from agent_platform.trust.verification import VerificationOutcome
from agent_platform.trust.verification_executor import (
    ProfileVerificationExecutor,
    SubprocessVerificationProcessRunner,
)


async def _run() -> int:
    workspace = Path.cwd().resolve()

    executor = ProfileVerificationExecutor(
        runner=SubprocessVerificationProcessRunner(
            timeout_seconds=300.0,
            terminate_grace_seconds=5.0,
        )
    )
    verifier = AuthoritativeVerifier(executor=executor)

    result = await verifier.verify(workspace=workspace)

    payload = {
        "workspace": str(workspace),
        "profile_version": result.profile_version,
        "outcome": result.outcome.value,
        "reason_code": result.reason_code,
        "steps": [
            {
                "check": step.check.value,
                "outcome": step.outcome.value,
                "exit_code": step.exit_code,
                "summary": step.summary,
            }
            for step in result.steps
        ],
    }

    print(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
    )

    return 0 if result.outcome is VerificationOutcome.PASS else 1


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
