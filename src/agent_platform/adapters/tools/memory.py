from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from agent_platform.contracts.memory import (
    MemoryStoreContract,
    RetrievalAcceptanceContract,
    RetrievalContract,
)
from agent_platform.contracts.tool import ToolContract
from agent_platform.domain.memory import (
    MemoryRecord,
    MemoryScope,
    RetrievalDecision,
    RetrievalQuery,
)
from agent_platform.domain.tool import (
    ToolDefinition,
    ToolRequest,
    ToolResult,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _RememberArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: str = Field(min_length=1)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class _RecallArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: str = Field(min_length=1)
    query: str = Field(min_length=1)
    limit: int = Field(default=5, gt=0)


class MemoryRememberTool(ToolContract):
    def __init__(
        self,
        store: MemoryStoreContract,
        *,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._store = store
        self._id_factory = id_factory
        self._clock = clock

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="memory_remember",
            description=(
                "Persist durable information in an explicit memory namespace for later recall."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "content": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "metadata": {
                        "type": "object",
                    },
                },
                "required": [
                    "namespace",
                    "content",
                ],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                    },
                    "namespace": {
                        "type": "string",
                    },
                    "created_at": {
                        "type": "string",
                    },
                },
                "required": [
                    "memory_id",
                    "namespace",
                    "created_at",
                ],
                "additionalProperties": False,
            },
        )

    async def invoke(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        arguments = _RememberArguments.model_validate(request.arguments)

        memory = MemoryRecord(
            id=self._id_factory(),
            scope=MemoryScope(
                namespace=arguments.namespace,
            ),
            content=arguments.content,
            created_at=self._clock(),
            metadata=arguments.metadata,
        )

        await self._store.store(memory)

        return ToolResult(
            run_id=request.run_id,
            tool_name=self.definition.name,
            output={
                "memory_id": str(memory.id),
                "namespace": memory.scope.namespace,
                "created_at": memory.created_at.isoformat(),
            },
        )


class MemoryRecallTool(ToolContract):
    def __init__(
        self,
        retrieval: RetrievalContract,
        acceptance: RetrievalAcceptanceContract,
    ) -> None:
        self._retrieval = retrieval
        self._acceptance = acceptance

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="memory_recall",
            description=(
                "Recall durable information from an explicit memory namespace "
                "using concise lexical search terms. The capability may abstain "
                "when retrieved evidence is insufficient."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "query": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 5,
                    },
                },
                "required": [
                    "namespace",
                    "query",
                ],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "decision": {
                        "type": "string",
                        "enum": [
                            "accept",
                            "abstain",
                        ],
                    },
                    "reason_code": {
                        "type": "string",
                    },
                    "metadata": {
                        "type": "object",
                    },
                    "memories": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "memory_id": {
                                    "type": "string",
                                },
                                "namespace": {
                                    "type": "string",
                                },
                                "content": {
                                    "type": "string",
                                },
                                "created_at": {
                                    "type": "string",
                                },
                                "metadata": {
                                    "type": "object",
                                },
                                "score": {
                                    "type": "number",
                                },
                                "rank": {
                                    "type": "integer",
                                },
                            },
                            "required": [
                                "memory_id",
                                "namespace",
                                "content",
                                "created_at",
                                "metadata",
                                "score",
                                "rank",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "decision",
                    "reason_code",
                    "metadata",
                    "memories",
                ],
                "additionalProperties": False,
            },
        )

    async def invoke(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        arguments = _RecallArguments.model_validate(request.arguments)

        query = RetrievalQuery(
            scope=MemoryScope(
                namespace=arguments.namespace,
            ),
            text=arguments.query,
            limit=arguments.limit,
        )

        hits = await self._retrieval.retrieve(query)
        decision = await self._acceptance.evaluate(
            query,
            hits,
        )

        memories: list[dict[str, Any]] = []

        if decision.decision is RetrievalDecision.ACCEPT:
            memories = [
                {
                    "memory_id": str(hit.memory.id),
                    "namespace": hit.memory.scope.namespace,
                    "content": hit.memory.content,
                    "created_at": hit.memory.created_at.isoformat(),
                    "metadata": hit.memory.metadata,
                    "score": hit.score,
                    "rank": hit.rank,
                }
                for hit in hits
            ]

        return ToolResult(
            run_id=request.run_id,
            tool_name=self.definition.name,
            output={
                "decision": decision.decision.value,
                "reason_code": decision.reason_code,
                "metadata": decision.metadata,
                "memories": memories,
            },
        )
