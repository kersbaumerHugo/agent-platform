from typing import Protocol

from agent_platform.domain.tool import (
    ToolDefinition,
    ToolRequest,
    ToolResult,
)


class ToolContract(Protocol):
    @property
    def definition(self) -> ToolDefinition: ...

    async def invoke(
        self,
        request: ToolRequest,
    ) -> ToolResult: ...
