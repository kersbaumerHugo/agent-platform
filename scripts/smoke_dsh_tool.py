import asyncio
from pathlib import Path
from uuid import uuid4

from agent_platform.adapters.runtimes.dsh import (
    DSHRuntime,
)
from agent_platform.domain.models import RuntimeRequest


async def main() -> None:
    run_id = uuid4()

    runtime = DSHRuntime(
        dsh_home=Path(".runtime/dsh-tools"),
        cwd=Path("."),
        provider="deepseek-official",
        model="openrouter/free",
        patches=(Path("config/dsh/platform-mcp.cordis.yml"),),
        request_timeout_seconds=180.0,
    )

    result = await runtime.execute(
        RuntimeRequest(
            run_id=run_id,
            agent_id="dsh-tool-smoke",
            input=(
                "This is an infrastructure validation. "
                "You MUST call the tool "
                "mcp__platform__diagnostic_echo exactly once "
                "with message exactly: "
                "'agentic tool path works'. "
                "Do not use shell commands. "
                "After the tool succeeds, reply exactly: "
                "Agentic tool call succeeded."
            ),
        )
    )

    print(f"run_id: {run_id}")
    print(f"runtime: {runtime.name}")
    print(f"output: {result.output}")


if __name__ == "__main__":
    asyncio.run(main())
