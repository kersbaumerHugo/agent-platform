from collections.abc import Iterable
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field

from agent_platform.contracts.tool import ToolContract
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
    EvaluationResult,
)
from agent_platform.domain.tool import ToolRequest


class ToolEvaluationInput(BaseModel):
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolEvaluationExpected(BaseModel):
    succeeds: bool = True
    output_contains: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = None


class ToolEvaluator:
    name = "tool"

    def __init__(
        self,
        tools: Iterable[ToolContract],
    ) -> None:
        self._tools: dict[str, ToolContract] = {}

        for tool in tools:
            tool_name = tool.definition.name

            if tool_name in self._tools:
                raise ValueError(f"Duplicate tool for evaluation: {tool_name}")

            self._tools[tool_name] = tool

    async def evaluate(
        self,
        case: EvaluationCase,
    ) -> EvaluationResult:
        evaluation_input = ToolEvaluationInput.model_validate(
            case.input,
        )
        expected = ToolEvaluationExpected.model_validate(
            case.expected,
        )

        try:
            tool = self._tools[evaluation_input.tool_name]
        except KeyError as exc:
            raise KeyError(f"Unknown evaluation tool: {evaluation_input.tool_name}") from exc

        request = ToolRequest(
            run_id=uuid5(
                NAMESPACE_URL,
                f"agent-platform-eval:{case.case_id}",
            ),
            arguments=evaluation_input.arguments,
        )

        try:
            result = await tool.invoke(request)
        except Exception as exc:
            actual_error_type = type(exc).__name__
            expected_error_match = (
                expected.error_type is None or actual_error_type == expected.error_type
            )
            expectations_met = not expected.succeeds and expected_error_match

            return EvaluationResult(
                case_id=case.case_id,
                evaluator=self.name,
                outcome=(EvaluationOutcome.PASS if expectations_met else EvaluationOutcome.FAIL),
                reason_code=(
                    "expected_tool_error" if expectations_met else "unexpected_tool_error"
                ),
                metrics={
                    "invocation_succeeded": 0.0,
                    "expected_error_match": float(expected_error_match),
                },
                metadata={
                    "tool_name": evaluation_input.tool_name,
                    "error_type": actual_error_type,
                },
            )

        run_id_match = result.run_id == request.run_id
        tool_name_match = result.tool_name == evaluation_input.tool_name
        output_match = all(
            key in result.output and result.output[key] == value
            for key, value in expected.output_contains.items()
        )

        expectations_met = expected.succeeds and run_id_match and tool_name_match and output_match

        return EvaluationResult(
            case_id=case.case_id,
            evaluator=self.name,
            outcome=(EvaluationOutcome.PASS if expectations_met else EvaluationOutcome.FAIL),
            reason_code=("expectations_met" if expectations_met else "expectation_mismatch"),
            metrics={
                "invocation_succeeded": 1.0,
                "run_id_match": float(run_id_match),
                "tool_name_match": float(tool_name_match),
                "output_match": float(output_match),
            },
            metadata={
                "tool_name": evaluation_input.tool_name,
            },
        )
