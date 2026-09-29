from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent_platform.domain.tool import ToolContinuation, ToolRequest, ToolResult


def test_tool_request_carries_trusted_principal_identity() -> None:
    request = ToolRequest(
        run_id=uuid4(),
        principal_id="agent:writer",
    )

    assert request.principal_id == "agent:writer"


def test_tool_request_normalizes_principal_identity() -> None:
    request = ToolRequest(
        run_id=uuid4(),
        principal_id="  evaluation:case-1  ",
    )

    assert request.principal_id == "evaluation:case-1"


def test_tool_request_rejects_blank_principal_identity() -> None:
    with pytest.raises(
        ValidationError,
        match="principal_id must not be blank",
    ):
        ToolRequest(
            run_id=uuid4(),
            principal_id="   ",
        )


def test_tool_request_allows_missing_principal_for_unprotected_legacy_flows() -> None:
    request = ToolRequest(
        run_id=uuid4(),
    )

    assert request.principal_id is None


def test_tool_result_default_continuation_is_continue() -> None:
    result = ToolResult(
        run_id=uuid4(),
        tool_name="test_tool",
        output={"key": "value"},
    )

    assert result.continuation == ToolContinuation.CONTINUE
    assert result.continuation == "continue"


def test_tool_result_explicit_finalize() -> None:
    result = ToolResult(
        run_id=uuid4(),
        tool_name="test_tool",
        output={"key": "value"},
        continuation=ToolContinuation.FINALIZE,
    )

    assert result.continuation == ToolContinuation.FINALIZE
    assert result.continuation == "finalize"


def test_tool_result_json_serialization_for_continue() -> None:
    result = ToolResult(
        run_id=uuid4(),
        tool_name="test_tool",
        output={"key": "value"},
    )

    json_str = result.model_dump_json()
    parsed = ToolResult.model_validate_json(json_str)

    assert parsed.continuation == ToolContinuation.CONTINUE
    assert parsed.continuation == "continue"


def test_tool_result_json_serialization_for_finalize() -> None:
    result = ToolResult(
        run_id=uuid4(),
        tool_name="test_tool",
        output={"key": "value"},
        continuation=ToolContinuation.FINALIZE,
    )

    json_str = result.model_dump_json()
    parsed = ToolResult.model_validate_json(json_str)

    assert parsed.continuation == ToolContinuation.FINALIZE
    assert parsed.continuation == "finalize"
