import hmac
import json
import os
from collections.abc import Iterator
from time import time
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from agent_platform.adapters.models.openrouter import OpenRouterModelAdapter
from agent_platform.adapters.observability.default import default_observer
from agent_platform.application.model_gateway import ModelGateway
from agent_platform.domain.model import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelResult,
    ModelToolCall,
    ModelToolDefinition,
)


class OpenAICompatFunctionCall(BaseModel):
    name: str
    arguments: str


class OpenAICompatToolCall(BaseModel):
    id: str
    type: str = "function"
    function: OpenAICompatFunctionCall


class OpenAICompatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: str | None = None

    tool_call_id: str | None = None
    tool_calls: list[OpenAICompatToolCall] = Field(default_factory=list)

    reasoning_content: str | None = None


class OpenAICompatFunctionDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, object]


class OpenAICompatTool(BaseModel):
    type: str
    function: OpenAICompatFunctionDefinition


class OpenAICompatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[OpenAICompatMessage] = Field(min_length=1)

    stream: bool = True
    temperature: float | None = None
    max_tokens: int | None = None

    tools: list[OpenAICompatTool] | None = None
    tool_choice: object | None = None
    stop: str | list[str] | None = None


router = APIRouter(
    prefix="/internal/v1",
    tags=["internal-model-gateway"],
)


def get_model_gateway() -> ModelGateway:
    api_key = os.environ.get("OPENROUTER_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY is not configured.",
        )

    model = os.environ.get(
        "OPENROUTER_MODEL",
        "openrouter/free",
    )

    return ModelGateway(
        OpenRouterModelAdapter(
            api_key=api_key,
            model=model,
            timeout_seconds=90.0,
        ),
        observer=default_observer,
    )


def require_gateway_auth(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = os.environ.get("MODEL_GATEWAY_API_KEY")

    if not expected:
        raise HTTPException(
            status_code=503,
            detail="MODEL_GATEWAY_API_KEY is not configured.",
        )

    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing model gateway bearer token.",
        )

    supplied = authorization.removeprefix("Bearer ").strip()

    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid model gateway bearer token.",
        )


def resolve_run_id(session_id: str | None) -> UUID:
    if session_id is None:
        return uuid4()

    try:
        return UUID(session_id)
    except ValueError:
        return uuid4()


def map_tools(
    tools: list[OpenAICompatTool] | None,
) -> list[ModelToolDefinition]:
    if not tools:
        return []

    mapped: list[ModelToolDefinition] = []

    for tool in tools:
        if tool.type != "function":
            raise HTTPException(
                status_code=501,
                detail=("Only function tools are supported."),
            )

        mapped.append(
            ModelToolDefinition(
                name=tool.function.name,
                description=tool.function.description,
                input_schema=tool.function.parameters,
            )
        )

    return mapped


def map_messages(
    messages: list[OpenAICompatMessage],
) -> list[ModelMessage]:
    mapped: list[ModelMessage] = []

    for message in messages:
        try:
            role = MessageRole(message.role)
        except ValueError as exc:
            raise HTTPException(
                status_code=501,
                detail=(f"Unsupported message role: {message.role}"),
            ) from exc

        if role in {
            MessageRole.SYSTEM,
            MessageRole.USER,
        }:
            if message.content is None or not message.content.strip():
                continue

            mapped.append(
                ModelMessage(
                    role=role,
                    content=message.content,
                )
            )
            continue

        if role == MessageRole.ASSISTANT:
            tool_calls: list[ModelToolCall] = []

            for tool_call in message.tool_calls:
                if tool_call.type != "function":
                    raise HTTPException(
                        status_code=501,
                        detail=("Only function tool calls are supported."),
                    )

                tool_calls.append(
                    ModelToolCall(
                        id=tool_call.id,
                        name=(tool_call.function.name),
                        arguments=(tool_call.function.arguments),
                    )
                )

            if (message.content is None or not message.content.strip()) and not tool_calls:
                continue

            mapped.append(
                ModelMessage(
                    role=role,
                    content=message.content,
                    tool_calls=tool_calls,
                    reasoning_content=(message.reasoning_content),
                )
            )
            continue

        if role == MessageRole.TOOL:
            if message.tool_call_id is None:
                raise HTTPException(
                    status_code=400,
                    detail=("Tool messages require tool_call_id."),
                )

            if message.content is None:
                raise HTTPException(
                    status_code=400,
                    detail=("Tool messages require content."),
                )

            mapped.append(
                ModelMessage(
                    role=role,
                    content=message.content,
                    tool_call_id=(message.tool_call_id),
                )
            )

    if not mapped:
        raise HTTPException(
            status_code=400,
            detail=("No model-compatible messages were provided."),
        )

    return mapped


def stream_result(
    result: ModelResult,
) -> Iterator[str]:
    request_id = result.provider_request_id or f"chatcmpl-{uuid4().hex}"

    created = int(time())

    delta: dict[str, object] = {
        "role": "assistant",
    }

    if result.output:
        delta["content"] = result.output

    if result.reasoning_content is not None:
        delta["reasoning_content"] = result.reasoning_content

    if result.tool_calls:
        delta["tool_calls"] = [
            {
                "index": index,
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                },
            }
            for index, tool_call in enumerate(result.tool_calls)
        ]

    content_chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": result.model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": None,
            }
        ],
    }

    yield (f"data: {json.dumps(content_chunk)}\n\n")

    finish_chunk: dict[str, object] = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": result.model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": (result.finish_reason or "stop"),
            }
        ],
    }

    if result.usage is not None:
        finish_chunk["usage"] = {
            "prompt_tokens": (result.usage.prompt_tokens),
            "completion_tokens": (result.usage.completion_tokens),
            "total_tokens": (result.usage.total_tokens),
        }

    yield (f"data: {json.dumps(finish_chunk)}\n\n")
    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def chat_completions(
    request: OpenAICompatRequest,
    gateway: Annotated[ModelGateway, Depends(get_model_gateway)],
    _: Annotated[None, Depends(require_gateway_auth)],
    x_deepseek_harness_session_id: Annotated[
        str | None,
        Header(),
    ] = None,
) -> StreamingResponse:
    if not request.stream:
        raise HTTPException(
            status_code=400,
            detail="M2b compatibility endpoint requires streaming.",
        )

    model_request = ModelRequest(
        run_id=resolve_run_id(x_deepseek_harness_session_id),
        messages=map_messages(request.messages),
        tools=map_tools(request.tools),
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    result = await gateway.generate(model_request)

    return StreamingResponse(
        stream_result(result),
        media_type="text/event-stream",
    )
