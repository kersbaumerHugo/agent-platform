from pydantic import BaseModel, ConfigDict, Field


class CapabilityAuthorizationDecision(BaseModel):
    """Platform-owned authorization decision for one capability invocation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    policy_version: str = Field(min_length=1)
    principal_id: str | None
    capability_name: str = Field(min_length=1)
    allowed: bool
    reason_code: str = Field(min_length=1)
