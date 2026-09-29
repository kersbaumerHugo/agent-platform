"""Tests for ToolResult class."""

from uuid import uuid4

from agent_platform.domain.tool import ToolContinuation, ToolResult


class TestToolResultDefaults:
    """Test that ToolResult defaults to ToolContinuation.CONTINUE when continuation is omitted."""

    def test_default_continuation_is_continue(self):
        """ToolResult should default to CONTINUE when continuation is not specified."""
        result = ToolResult(run_id=uuid4(), tool_name="test_tool", output={"key": "value"})
        assert result.continuation == ToolContinuation.CONTINUE
        assert result.continuation.value == "continue"

    def test_default_continuation_string_value(self):
        """Verify the string representation of default continuation."""
        result = ToolResult(run_id=uuid4(), tool_name="test_tool", output={"key": "value"})
        assert result.continuation == "continue"


class TestToolResultExplicitFinalize:
    """Test that ToolResult accepts ToolContinuation.FINALIZE explicitly."""

    def test_explicit_finalize_value(self):
        """ToolResult should accept FINALIZE when explicitly provided."""
        result = ToolResult(
            run_id=uuid4(),
            tool_name="test_tool",
            output={"key": "value"},
            continuation=ToolContinuation.FINALIZE,
        )
        assert result.continuation == ToolContinuation.FINALIZE
        assert result.continuation.value == "finalize"

    def test_explicit_finalize_string(self):
        """ToolResult should accept "finalize" string directly."""
        result = ToolResult(
            run_id=uuid4(), tool_name="test_tool", output={"key": "value"}, continuation="finalize"
        )
        assert result.continuation == ToolContinuation.FINALIZE
        assert result.continuation.value == "finalize"


class TestToolResultJsonSerialization:
    """Test JSON serialization of ToolResult continuation field."""

    def test_default_continuation_serializes_as_continue(self):
        """model_dump(mode='json') should serialize continuation as 'continue' for default case."""
        result = ToolResult(run_id=uuid4(), tool_name="test_tool", output={"key": "value"})
        json_data = result.model_dump(mode="json")
        assert json_data["continuation"] == "continue"
        assert isinstance(json_data["continuation"], str)

    def test_finalize_continuation_serializes_as_finalize(self):
        """model_dump(mode='json') should serialize continuation as 'finalize' for explicit case."""
        result = ToolResult(
            run_id=uuid4(),
            tool_name="test_tool",
            output={"key": "value"},
            continuation=ToolContinuation.FINALIZE,
        )
        json_data = result.model_dump(mode="json")
        assert json_data["continuation"] == "finalize"
        assert isinstance(json_data["continuation"], str)

    def test_continuation_not_included_when_default(self):
        """When continuation uses default, ensure it's properly serialized."""
        result = ToolResult(run_id=uuid4(), tool_name="test_tool", output={"key": "value"})
        json_data = result.model_dump(mode="json")
        assert "continuation" in json_data
        assert json_data["continuation"] == "continue"
