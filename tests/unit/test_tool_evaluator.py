import pytest
from pydantic import ValidationError

from agent_platform.adapters.evaluation.tool import ToolEvaluator
from agent_platform.application.eval_runner import EvalRunner
from agent_platform.domain.evaluation import (
    EvaluationCase,
    EvaluationOutcome,
)
from agent_platform.domain.tool import (
    ToolDefinition,
    ToolRequest,
    ToolResult,
)


class EchoTool:
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="echo",
            description="Echo a value.",
            input_schema={},
            output_schema={},
        )

    async def invoke(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        return ToolResult(
            run_id=request.run_id,
            tool_name=self.definition.name,
            output={
                "value": request.arguments.get("value"),
            },
        )


class FailingTool:
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="failing",
            description="Always fails.",
            input_schema={},
            output_schema={},
        )

    async def invoke(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        raise ValueError("boom")


class MismatchedTool:
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="mismatched",
            description="Returns invalid contract fields.",
            input_schema={},
            output_schema={},
        )

    async def invoke(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        return ToolResult(
            run_id=request.run_id,
            tool_name="different",
            output={"value": "wrong"},
        )


class PrincipalRecordingTool:
    def __init__(self) -> None:
        self.principal_ids: list[str | None] = []

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="principal-recording",
            description="Record the invocation principal.",
            input_schema={},
            output_schema={},
        )

    async def invoke(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        self.principal_ids.append(request.principal_id)

        return ToolResult(
            run_id=request.run_id,
            tool_name=self.definition.name,
            output={},
        )


@pytest.mark.asyncio
async def test_tool_evaluator_uses_stable_system_principal() -> None:
    tool = PrincipalRecordingTool()
    evaluator = ToolEvaluator([tool])

    await evaluator.evaluate(
        EvaluationCase(
            case_id="case-one",
            input={"tool_name": "principal-recording"},
        )
    )

    await evaluator.evaluate(
        EvaluationCase(
            case_id="case-two",
            input={"tool_name": "principal-recording"},
        )
    )

    assert tool.principal_ids == [
        "system:tool-evaluator",
        "system:tool-evaluator",
    ]


@pytest.mark.asyncio
async def test_tool_evaluator_passes_expected_output() -> None:
    evaluator = ToolEvaluator([EchoTool()])

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="echo-success",
            input={
                "tool_name": "echo",
                "arguments": {"value": "hello"},
            },
            expected={
                "succeeds": True,
                "output_contains": {"value": "hello"},
            },
        )
    )

    assert result.outcome is EvaluationOutcome.PASS
    assert result.reason_code == "expectations_met"
    assert result.metrics == {
        "invocation_succeeded": 1.0,
        "run_id_match": 1.0,
        "tool_name_match": 1.0,
        "output_match": 1.0,
    }


@pytest.mark.asyncio
async def test_tool_evaluator_passes_expected_failure() -> None:
    evaluator = ToolEvaluator([FailingTool()])

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="expected-failure",
            input={
                "tool_name": "failing",
            },
            expected={
                "succeeds": False,
                "error_type": "ValueError",
            },
        )
    )

    assert result.outcome is EvaluationOutcome.PASS
    assert result.reason_code == "expected_tool_error"
    assert result.metrics["invocation_succeeded"] == 0.0
    assert result.metrics["expected_error_match"] == 1.0
    assert result.metadata["error_type"] == "ValueError"


@pytest.mark.asyncio
async def test_tool_evaluator_fails_unexpected_error_type() -> None:
    evaluator = ToolEvaluator([FailingTool()])

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="wrong-error",
            input={
                "tool_name": "failing",
            },
            expected={
                "succeeds": False,
                "error_type": "RuntimeError",
            },
        )
    )

    assert result.outcome is EvaluationOutcome.FAIL
    assert result.reason_code == "unexpected_tool_error"
    assert result.metrics["expected_error_match"] == 0.0


@pytest.mark.asyncio
async def test_tool_evaluator_detects_contract_mismatch() -> None:
    evaluator = ToolEvaluator([MismatchedTool()])

    result = await evaluator.evaluate(
        EvaluationCase(
            case_id="contract-mismatch",
            input={
                "tool_name": "mismatched",
            },
            expected={
                "output_contains": {"value": "expected"},
            },
        )
    )

    assert result.outcome is EvaluationOutcome.FAIL
    assert result.metrics["tool_name_match"] == 0.0
    assert result.metrics["output_match"] == 0.0


@pytest.mark.asyncio
async def test_eval_runner_reports_unknown_tool_as_error() -> None:
    runner = EvalRunner(ToolEvaluator([EchoTool()]))

    results = await runner.run(
        [
            EvaluationCase(
                case_id="unknown-tool",
                input={
                    "tool_name": "missing",
                },
            )
        ]
    )

    assert len(results) == 1
    assert results[0].outcome is EvaluationOutcome.ERROR
    assert results[0].reason_code == "evaluator_exception"
    assert results[0].metadata == {
        "error_type": KeyError.__name__,
    }


def test_tool_evaluator_rejects_duplicate_tools() -> None:
    with pytest.raises(
        ValueError,
        match="Duplicate tool for evaluation: echo",
    ):
        ToolEvaluator([EchoTool(), EchoTool()])


@pytest.mark.asyncio
async def test_invalid_tool_case_is_reported_as_runner_error() -> None:
    runner = EvalRunner(ToolEvaluator([EchoTool()]))

    results = await runner.run(
        [
            EvaluationCase(
                case_id="invalid-tool-case",
                input={
                    "tool_name": "",
                },
            )
        ]
    )

    assert results[0].outcome is EvaluationOutcome.ERROR
    assert results[0].metadata == {
        "error_type": ValidationError.__name__,
    }
