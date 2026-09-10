import asyncio
import os
from uuid import uuid4

from agent_platform.adapters.models.openrouter import OpenRouterModelAdapter
from agent_platform.domain.model import MessageRole, ModelMessage, ModelRequest


async def main() -> None:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    model = os.environ.get("OPENROUTER_MODEL", "openrouter/free")

    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set.")

    adapter = OpenRouterModelAdapter(
        api_key=api_key,
        model=model,
        timeout_seconds=90.0,
    )

    result = await adapter.generate(
        ModelRequest(
            run_id=uuid4(),
            messages=[
                ModelMessage(
                    role=MessageRole.SYSTEM,
                    content=(
                        "You are participating in an infrastructure smoke test. Reply concisely."
                    ),
                ),
                ModelMessage(
                    role=MessageRole.USER,
                    content=("Reply exactly with: Agent Platform model gateway is working."),
                ),
            ],
            temperature=0,
            max_tokens=50,
        )
    )

    print(f"provider: {result.provider}")
    print(f"model: {result.model}")
    print(f"provider_request_id: {result.provider_request_id}")
    print(f"finish_reason: {result.finish_reason}")

    if result.usage is not None:
        print(f"prompt_tokens: {result.usage.prompt_tokens}")
        print(f"completion_tokens: {result.usage.completion_tokens}")
        print(f"total_tokens: {result.usage.total_tokens}")

    print(f"output: {result.output}")


if __name__ == "__main__":
    asyncio.run(main())
