from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent_platform.domain.tool import ToolRequest


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
