from datetime import UTC, datetime

import httpx
import pytest

from agent_platform.adapters.github.issues import GitHubIssueWorkItemProvider


@pytest.mark.asyncio
async def test_valid_mapping() -> None:
    """Test valid GitHub issue mapping to WorkItem."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "number": 42,
                "html_url": "https://github.com/owner/repo/issues/42",
                "title": "Test Issue Title",
                "body": "Test Issue Body",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = GitHubIssueWorkItemProvider(repository="owner/repo", client=client)

    try:
        result = await provider.fetch(issue_number=42)

        assert result.source == "github"
        assert result.repository == "owner/repo"
        assert result.issue_number == 42
        assert result.canonical_url == "https://github.com/owner/repo/issues/42"
        assert result.title == "Test Issue Title"
        assert result.body == "Test Issue Body"
        expected_dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert result.updated_at == expected_dt
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_exact_request_url() -> None:
    """Test that the request URL is exactly as expected."""

    captured_url: str | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_url
        captured_url = str(request.url)
        return httpx.Response(
            200,
            json={
                "number": 99,
                "html_url": "https://example.com/99",
                "title": "Test",
                "body": "Test",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = GitHubIssueWorkItemProvider(repository="owner/repo", client=client)

    try:
        await provider.fetch(issue_number=99)
        assert captured_url == "https://api.github.com/repos/owner/repo/issues/99"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_required_headers() -> None:
    """Test that required headers are present in the request."""

    captured_headers: dict[str, str] | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_headers
        captured_headers = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "number": 1,
                "html_url": "https://example.com/1",
                "title": "Test",
                "body": "Test",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = GitHubIssueWorkItemProvider(
        repository="owner/repo",
        token="secret-token",
        client=client,
    )

    try:
        await provider.fetch(issue_number=1)
        assert captured_headers["accept"] == "application/vnd.github+json"
        assert captured_headers["x-github-api-version"] == "2022-11-28"
        assert captured_headers["authorization"] == "Bearer secret-token"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_no_auth_header_when_no_token() -> None:
    """Test that Authorization header is absent when no token is provided."""

    captured_headers: dict[str, str] | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_headers
        captured_headers = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "number": 1,
                "html_url": "https://example.com/1",
                "title": "Test",
                "body": "Test",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = GitHubIssueWorkItemProvider(repository="owner/repo", client=client)

    try:
        await provider.fetch(issue_number=1)
        assert "Authorization" not in captured_headers
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_null_body() -> None:
    """Test that null body in payload results in empty string."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "number": 1,
                "html_url": "https://example.com/1",
                "title": "Test",
                "body": None,
                "updated_at": "2024-01-01T00:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = GitHubIssueWorkItemProvider(repository="owner/repo", client=client)

    try:
        result = await provider.fetch(issue_number=1)
        assert result.body == ""
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_pull_request_key_present() -> None:
    """Test that presence of pull_request key raises ValueError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "number": 1,
                "html_url": "https://example.com/1",
                "title": "Test",
                "body": "Test",
                "updated_at": "2024-01-01T00:00:00Z",
                "pull_request": None,
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = GitHubIssueWorkItemProvider(repository="owner/repo", client=client)

    try:
        with pytest.raises(ValueError):
            await provider.fetch(issue_number=1)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_number_mismatch() -> None:
    """Test that payload issue number mismatch raises ValueError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "number": 2,
                "html_url": "https://example.com/2",
                "title": "Test",
                "body": "Test",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = GitHubIssueWorkItemProvider(repository="owner/repo", client=client)

    try:
        with pytest.raises(ValueError):
            await provider.fetch(issue_number=1)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_invalid_issue_number_before_http() -> None:
    """Test that invalid issue numbers (0 and -1) raise ValueError before HTTP."""

    request_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json={
                "number": 1,
                "html_url": "https://example.com/1",
                "title": "Test",
                "body": "Test",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = GitHubIssueWorkItemProvider(repository="owner/repo", client=client)

    try:
        with pytest.raises(ValueError):
            await provider.fetch(issue_number=0)
        with pytest.raises(ValueError):
            await provider.fetch(issue_number=-1)
        assert request_count == 0
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "invalid_repository",
    [
        "",
        "   ",
        "owner",
        "/repo",
        "owner/",
        "owner//repo",
        "owner/repo/extra",
        " owner/repo",
        "owner /repo",
        "owner/ repo",
        "owner/repo ",
    ],
)
def test_invalid_repository_values(invalid_repository: str) -> None:
    """Test that invalid repository values raise ValueError synchronously."""
    with pytest.raises(ValueError):
        GitHubIssueWorkItemProvider(repository=invalid_repository)


@pytest.mark.parametrize(
    "invalid_timeout",
    [
        0,
        -1,
        -0.1,
    ],
)
def test_invalid_timeout_values(invalid_timeout: float) -> None:
    """Test that invalid timeout values raise ValueError synchronously."""
    with pytest.raises(ValueError):
        GitHubIssueWorkItemProvider(repository="test/test", timeout_seconds=invalid_timeout)


@pytest.mark.asyncio
async def test_injected_client_lifecycle() -> None:
    """Test lifecycle for an externally injected client.

    The provider should:
    - use the exact injected client object
    - not close the client via aclose()
    - leave client.is_closed as False before explicit close
    """
    client = httpx.AsyncClient()
    provider = GitHubIssueWorkItemProvider(
        repository="owner/repo",
        client=client,
    )

    try:
        # Assert the provider stores/uses the exact injected client object
        assert provider._client is client

        # Assert client.is_closed is False before provider.aclose()
        assert client.is_closed is False

        # Call aclose - should not close the injected client
        await provider.aclose()

        # client.is_closed is still False because provider didn't own it
        assert client.is_closed is False
    finally:
        # Explicitly close the client in test cleanup
        await client.aclose()

        # Finally assert client.is_closed is True
        assert client.is_closed is True


@pytest.mark.asyncio
async def test_owned_client_lifecycle() -> None:
    """Test lifecycle for an owned (provider-created) client.

    The provider should:
    - own the client it creates
    - leave client.is_closed as False initially
    - close the client via aclose()
    - leave client.is_closed as True after aclose()
    """
    provider = GitHubIssueWorkItemProvider(
        repository="owner/repo",
    )

    try:
        # Capture the provider-created AsyncClient reference
        assert provider._client is not None

        # Assert the provider owns that client
        assert provider._owns_client is True

        # Assert client.is_closed is False initially
        assert provider._client.is_closed is False

        # Call aclose - should close the owned client
        await provider.aclose()

        # Assert client.is_closed is True
        assert provider._client.is_closed is True
    finally:
        # Ensure cleanup even if tests fail
        if provider._client and not provider._client.is_closed:
            await provider._client.aclose()


@pytest.mark.asyncio
async def test_timeout_propagation() -> None:
    """Test that provider timeout is propagated to outgoing request."""

    captured_timeout: dict[str, float] | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_timeout
        captured_timeout = dict(request.extensions["timeout"])
        return httpx.Response(
            200,
            json={
                "number": 42,
                "html_url": "https://github.com/owner/repo/issues/42",
                "title": "Test Issue Title",
                "body": "Test Issue Body",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = GitHubIssueWorkItemProvider(
        repository="owner/repo",
        client=client,
        timeout_seconds=3.25,
    )

    try:
        await provider.fetch(issue_number=42)
        assert captured_timeout is not None
        assert abs(captured_timeout["connect"] - 3.25) < 0.01
        assert abs(captured_timeout["read"] - 3.25) < 0.01
        assert abs(captured_timeout["write"] - 3.25) < 0.01
        assert abs(captured_timeout["pool"] - 3.25) < 0.01
    finally:
        await client.aclose()
