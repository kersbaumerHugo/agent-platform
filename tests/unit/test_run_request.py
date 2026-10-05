import pytest
from pydantic import ValidationError

from agent_platform.domain.models import RunRequest


@pytest.mark.parametrize(
    "agent_id",
    [" ", "   ", "\t", "\n", " \t\n "],
)
def test_run_request_rejects_blank_agent_id(agent_id: str) -> None:
    with pytest.raises(ValidationError):
        RunRequest(
            agent_id=agent_id,
            input="do work",
        )


@pytest.mark.parametrize(
    "input_value",
    [" ", "   ", "\t", "\n", " \t\n "],
)
def test_run_request_rejects_blank_input(input_value: str) -> None:
    with pytest.raises(ValidationError):
        RunRequest(
            agent_id="developer-agent",
            input=input_value,
        )


def test_run_request_preserves_valid_nonblank_values() -> None:
    request = RunRequest(
        agent_id=" developer-agent ",
        input=" implement feature\nwith context ",
    )

    assert request.agent_id == " developer-agent "
    assert request.input == " implement feature\nwith context "
