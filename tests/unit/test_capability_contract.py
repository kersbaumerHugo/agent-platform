from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from agent_platform.contracts.capability import CapabilityContract
from agent_platform.domain.capability import CapabilityDefinition


@dataclass(frozen=True)
class ExampleRequest:
    value: str


@dataclass(frozen=True)
class ExampleResult:
    value: str


class ExampleCapability:
    @property
    def definition(self) -> CapabilityDefinition:
        return CapabilityDefinition(
            name="example.echo",
            description="Return one typed platform result.",
        )

    async def invoke(
        self,
        request: ExampleRequest,
    ) -> ExampleResult:
        return ExampleResult(value=request.value)


@pytest.mark.asyncio
async def test_capability_contract_preserves_typed_request_and_result() -> None:
    capability: CapabilityContract[ExampleRequest, ExampleResult] = ExampleCapability()

    result = await capability.invoke(
        ExampleRequest(value="typed"),
    )

    assert capability.definition.name == "example.echo"
    assert result == ExampleResult(value="typed")


def test_capability_definition_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CapabilityDefinition.model_validate(
            {
                "name": "example.echo",
                "description": "Typed capability.",
                "input_schema": {},
            }
        )


def test_capability_definition_is_immutable() -> None:
    definition = CapabilityDefinition(
        name="example.echo",
        description="Typed capability.",
    )

    with pytest.raises(
        ValidationError,
        match="Instance is frozen",
    ):
        definition.name = "changed"  # type: ignore[misc]
