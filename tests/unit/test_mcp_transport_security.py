from agent_platform.api.mcp import (
    build_transport_security,
)


def test_mcp_transport_security_defaults_to_local_hosts(
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "AGENT_PLATFORM_MCP_ALLOWED_HOST",
        raising=False,
    )

    settings = build_transport_security()

    assert settings.enable_dns_rebinding_protection
    assert settings.allowed_hosts == [
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
    ]


def test_mcp_transport_security_adds_configured_host(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "AGENT_PLATFORM_MCP_ALLOWED_HOST",
        "192.168.10.30:8001",
    )

    settings = build_transport_security()

    assert "192.168.10.30:8001" in settings.allowed_hosts
