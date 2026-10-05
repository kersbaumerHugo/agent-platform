import pytest
from pydantic import ValidationError

from agent_platform.domain.models import RunRequest


class TestRunRequestValidation:
    """Test RunRequest validation for whitespace rejection."""

    def test_agent_id_whitespace_only_rejected(self):
        """Reject agent_id that is whitespace-only."""
        with pytest.raises(ValidationError):
            RunRequest(agent_id="   ", input="test")

    def test_agent_id_tabs_and_newlines_rejected(self):
        """Reject agent_id with tabs and newlines only."""
        with pytest.raises(ValidationError):
            RunRequest(agent_id="\t\n", input="test")

    def test_agent_id_mixed_whitespace_rejected(self):
        """Reject agent_id with mixed whitespace characters."""
        with pytest.raises(ValidationError):
            RunRequest(agent_id="   \t\n   ", input="test")

    def test_input_whitespace_only_rejected(self):
        """Reject input that is whitespace-only."""
        with pytest.raises(ValidationError):
            RunRequest(agent_id="test-agent", input="   ")

    def test_input_tabs_and_newlines_rejected(self):
        """Reject input with tabs and newlines only."""
        with pytest.raises(ValidationError):
            RunRequest(agent_id="test-agent", input="\t\n")

    def test_input_mixed_whitespace_rejected(self):
        """Reject input with mixed whitespace characters."""
        with pytest.raises(ValidationError):
            RunRequest(agent_id="test-agent", input="   \t\n   ")

    def test_agent_id_valid_nonblank_accepted(self):
        """Accept valid nonblank agent_id."""
        request = RunRequest(agent_id="test-agent", input="test")
        assert request.agent_id == "test-agent"

    def test_agent_id_with_leading_space_accepted(self):
        """Accept agent_id with leading space."""
        request = RunRequest(agent_id=" test-agent", input="test")
        assert request.agent_id == " test-agent"

    def test_agent_id_with_trailing_space_accepted(self):
        """Accept agent_id with trailing space."""
        request = RunRequest(agent_id="test-agent ", input="test")
        assert request.agent_id == "test-agent "

    def test_agent_id_with_padded_spaces_accepted(self):
        """Accept agent_id with padded spaces."""
        request = RunRequest(agent_id="  test-agent  ", input="test")
        assert request.agent_id == "  test-agent  "

    def test_input_valid_nonblank_accepted(self):
        """Accept valid nonblank input."""
        request = RunRequest(agent_id="test-agent", input="test")
        assert request.input == "test"

    def test_input_with_leading_space_accepted(self):
        """Accept input with leading space."""
        request = RunRequest(agent_id="test-agent", input=" test")
        assert request.input == " test"

    def test_input_with_trailing_space_accepted(self):
        """Accept input with trailing space."""
        request = RunRequest(agent_id="test-agent", input="test ")
        assert request.input == "test "

    def test_input_with_padded_spaces_accepted(self):
        """Accept input with padded spaces."""
        request = RunRequest(agent_id="test-agent", input="  test  ")
        assert request.input == "  test  "

    def test_input_with_newline_accepted(self):
        """Accept input containing newline."""
        request = RunRequest(agent_id="test-agent", input="test\nmore")
        assert request.input == "test\nmore"

    def test_empty_agent_id_rejected(self):
        """Reject empty agent_id (already handled by min_length=1)."""
        with pytest.raises(ValidationError):
            RunRequest(agent_id="", input="test")

    def test_empty_input_rejected(self):
        """Reject empty input (already handled by min_length=1)."""
        with pytest.raises(ValidationError):
            RunRequest(agent_id="test-agent", input="")
