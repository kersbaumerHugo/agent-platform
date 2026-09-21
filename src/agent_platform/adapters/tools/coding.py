from pydantic import BaseModel, ConfigDict, Field

from agent_platform.contracts.capability import CapabilityContract
from agent_platform.contracts.tool import ToolContract
from agent_platform.domain.coding import CodingResult, CodingTask
from agent_platform.domain.tool import (
    ToolDefinition,
    ToolRequest,
    ToolResult,
)


class _CodingArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1)
    expected_base_revision: str = Field(
        min_length=40,
        max_length=40,
    )


class CodingTool(ToolContract):
    """Model-facing adapter for the typed supervised coding capability."""

    def __init__(
        self,
        capability: CapabilityContract[CodingTask, CodingResult],
    ) -> None:
        self._capability = capability

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="coding_execute",
            description=(
                "Execute one supervised coding task through the Agent Platform "
                "trusted coding capability."
            ),
            input_schema=_CodingArguments.model_json_schema(),
            output_schema=CodingResult.model_json_schema(),
        )

    async def invoke(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        arguments = _CodingArguments.model_validate(request.arguments)

        task = CodingTask(
            goal=arguments.goal,
            expected_base_revision=arguments.expected_base_revision,
        )

        result = await self._capability.invoke(task)

        return ToolResult(
            run_id=request.run_id,
            tool_name=self.definition.name,
            output=result.model_dump(mode="json"),
        )
