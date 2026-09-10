from pydantic import BaseModel, Field

from agent_platform.contracts.tool import ToolContract
from agent_platform.domain.tool import (
    ToolDefinition,
    ToolRequest,
    ToolResult,
)


class _EchoArguments(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=256,
    )


class DiagnosticEchoTool(ToolContract):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="diagnostic_echo",
            description=("Echo a diagnostic message through the Agent Platform tool layer."),
            input_schema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 256,
                    }
                },
                "required": ["message"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                    }
                },
                "required": ["message"],
                "additionalProperties": False,
            },
        )

    async def invoke(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        arguments = _EchoArguments.model_validate(request.arguments)

        return ToolResult(
            run_id=request.run_id,
            tool_name=self.definition.name,
            output={
                "message": arguments.message,
            },
        )
