from pydantic import BaseModel, ConfigDict, Field

from agent_platform.contracts.authorization import (
    CapabilityAuthorizationContract,
)
from agent_platform.contracts.capability import CapabilityContract
from agent_platform.contracts.tool import ToolContract
from agent_platform.domain.repository import (
    RepositoryInspectionRequest,
    RepositoryInspectionResult,
)
from agent_platform.domain.tool import (
    ToolDefinition,
    ToolRequest,
    ToolResult,
)


class _RepositoryInspectionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: tuple[str, ...] = Field(min_length=1)


class RepositoryInspectionTool(ToolContract):
    def __init__(
        self,
        capability: CapabilityContract[
            RepositoryInspectionRequest,
            RepositoryInspectionResult,
        ],
        authorization: CapabilityAuthorizationContract,
    ) -> None:
        self._capability = capability
        self._authorization = authorization

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="repository_inspect",
            description=("Inspect repository targets and return structured repository evidence."),
            input_schema=_RepositoryInspectionArguments.model_json_schema(),
            output_schema=RepositoryInspectionResult.model_json_schema(),
        )

    async def invoke(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        decision = self._authorization.authorize(
            principal_id=request.principal_id,
            capability=self._capability.definition,
        )

        if not decision.allowed:
            raise PermissionError(f"Capability invocation denied: {decision.reason_code}")

        arguments = _RepositoryInspectionArguments.model_validate(request.arguments)

        result = await self._capability.invoke(
            RepositoryInspectionRequest(
                targets=arguments.targets,
            )
        )

        return ToolResult(
            run_id=request.run_id,
            tool_name=self.definition.name,
            output=result.model_dump(mode="json"),
        )
