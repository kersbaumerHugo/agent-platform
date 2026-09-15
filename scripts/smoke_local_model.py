import asyncio
import os
from uuid import uuid4

from agent_platform.adapters.models.local_openai import (
    LocalOpenAIModelAdapter,
)
from agent_platform.adapters.observability.default import default_observer
from agent_platform.application.model_gateway import ModelGateway
from agent_platform.domain.model import (
    MessageRole,
    ModelMessage,
    ModelRequest,
)


async def main() -> None:
    api_key = os.environ.get("LOCAL_MODEL_API_KEY")
    base_url = os.environ.get("LOCAL_MODEL_BASE_URL")
    model = os.environ.get("LOCAL_MODEL_NAME")

    if not api_key:
        raise RuntimeError("LOCAL_MODEL_API_KEY is not set.")

    if not base_url:
        raise RuntimeError("LOCAL_MODEL_BASE_URL is not set.")

    if not model:
        raise RuntimeError("LOCAL_MODEL_NAME is not set.")

    adapter = LocalOpenAIModelAdapter(
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout_seconds=90.0,
        enable_thinking=False,
    )

    gateway = ModelGateway(
        model=adapter,
        observer=default_observer,
    )

    result = await gateway.generate(
        ModelRequest(
            run_id=uuid4(),
            messages=[
                ModelMessage(
                    role=MessageRole.SYSTEM,
                    content=(
                        "You are participating in an infrastructure "
                        "smoke test. Follow the user's instruction exactly."
                    ),
                ),
                ModelMessage(
                    role=MessageRole.USER,
                    content=(
                        "Responda exatamente: "
                        "Agent Platform local inference is working."
                    ),
                ),
            ],
            temperature=0,
            max_tokens=64,
        )
    )

    print(f"provider: {result.provider}")
    print(f"model: {result.model}")
    print(f"finish_reason: {result.finish_reason}")

    if result.usage is not None:
        print(f"prompt_tokens: {result.usage.prompt_tokens}")
        print(f"completion_tokens: {result.usage.completion_tokens}")
        print(f"total_tokens: {result.usage.total_tokens}")

    print(f"output: {result.output}")


if __name__ == "__main__":
    asyncio.run(main())
