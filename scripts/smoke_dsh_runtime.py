import asyncio
from pathlib import Path
from uuid import uuid4

from agent_platform.adapters.runtimes.dsh import DSHRuntime
from agent_platform.domain.models import RuntimeRequest


async def main() -> None:
    run_id = uuid4()

    runtime = DSHRuntime(
        dsh_home=Path(".runtime/dsh"),
        cwd=Path("."),
        provider="deepseek-official",
        model="openrouter/free",
        request_timeout_seconds=180.0,
    )

    result = await runtime.execute(
        RuntimeRequest(
            run_id=run_id,
            agent_id="dsh-smoke",
            input=(
                "This is an infrastructure smoke test. "
                "Do not modify any files and do not run shell commands. "
                "Reply exactly with: DSH runtime adapter is working."
            ),
        )
    )

    print(f"run_id: {run_id}")
    print(f"runtime: {runtime.name}")
    print(f"output: {result.output}")


if __name__ == "__main__":
    asyncio.run(main())
