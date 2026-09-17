from uuid import UUID

from fastapi.testclient import TestClient

from agent_platform.api.main import app
from agent_platform.api.openai_compat import (
    get_model_gateway,
    get_run_context_bindings,
)
from agent_platform.application.model_gateway import ModelGateway
from agent_platform.application.run_context import (
    InMemoryRunContextBindings,
)
from agent_platform.domain.context import content_sha256
from agent_platform.domain.context_preparation import (
    ContextPreparationResult,
)
from agent_platform.domain.context_rendering import RenderedContext
from agent_platform.domain.context_trace import (
    ContextBudgetTrace,
    ContextInjectionTrace,
    ContextPreparationTrace,
    ContextRenderingTrace,
)
from agent_platform.domain.model import (
    MessageRole,
    ModelRequest,
    ModelResult,
)
from agent_platform.domain.observability import ObservationEvent


class CapturingModel:
    provider = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def generate(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        self.requests.append(request)
        return ModelResult(
            provider=self.provider,
            model=self.model,
            output="ok",
            finish_reason="stop",
        )


class NullObserver:
    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        pass


def make_prepared_context(
    text: str,
) -> ContextPreparationResult:
    content_hash = content_sha256(text)
    rendered = RenderedContext(
        renderer="markdown",
        version="v0",
        text=text,
        content_hash=content_hash,
    )

    return ContextPreparationResult(
        rendered=rendered,
        trace=ContextPreparationTrace(
            version="v0",
            planner="deterministic",
            planner_version="v0",
            provider_traces=(),
            assembler_version="v0",
            budget=ContextBudgetTrace(
                policy_version="canonical-prefix-v0",
                estimator_version="utf8-bytes-v0",
                budget_tokens=128,
                estimated_tokens=1 if text else 0,
                dropped_item_ids=(),
            ),
            rendering=ContextRenderingTrace(
                renderer=rendered.renderer,
                version=rendered.version,
                content_hash=rendered.content_hash,
            ),
            injection=ContextInjectionTrace(
                injector="reference-message",
                version="v0",
            ),
        ),
    )


def install_dependencies(
    *,
    model: CapturingModel,
    bindings: InMemoryRunContextBindings,
) -> None:
    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway(
        model,
        NullObserver(),
    )
    app.dependency_overrides[get_run_context_bindings] = lambda: bindings


def post_completion(
    client: TestClient,
    *,
    session_id: str,
    user_content: str,
) -> object:
    return client.post(
        "/internal/v1/chat/completions",
        headers={
            "Authorization": "Bearer internal-test-token",
            "x-deepseek-harness-session-id": session_id,
        },
        json={
            "model": "logical-agent-model",
            "stream": True,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a test agent.",
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
        },
    )


def test_required_state_is_explicit_and_release_clears_it() -> None:
    bindings = InMemoryRunContextBindings()
    run_id = UUID("11111111-1111-1111-1111-111111111111")

    assert bindings.is_required(run_id) is False

    bindings.require(run_id)

    assert bindings.is_required(run_id) is True
    assert bindings.resolve(run_id) is None

    bindings.bind(
        run_id,
        make_prepared_context("context-a"),
    )
    bindings.release(run_id)

    assert bindings.resolve(run_id) is None
    assert bindings.is_required(run_id) is False


def test_gateway_injects_bound_context_before_last_user(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "MODEL_GATEWAY_API_KEY",
        "internal-test-token",
    )

    model = CapturingModel()
    bindings = InMemoryRunContextBindings()
    session_id = "11111111-1111-1111-1111-111111111111"
    context_text = "reference context for this run"

    bindings.bind(
        UUID(session_id),
        make_prepared_context(context_text),
    )
    install_dependencies(
        model=model,
        bindings=bindings,
    )

    try:
        response = post_completion(
            TestClient(app),
            session_id=session_id,
            user_content="do the work",
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(model.requests) == 1

    messages = model.requests[0].messages
    assert [message.role for message in messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.USER,
    ]
    assert messages[0].content == "You are a test agent."
    assert messages[1].content == context_text
    assert messages[2].content == "do the work"


def test_gateway_leaves_context_free_run_unchanged(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "MODEL_GATEWAY_API_KEY",
        "internal-test-token",
    )

    model = CapturingModel()
    bindings = InMemoryRunContextBindings()
    session_id = "11111111-1111-1111-1111-111111111111"

    install_dependencies(
        model=model,
        bindings=bindings,
    )

    try:
        response = post_completion(
            TestClient(app),
            session_id=session_id,
            user_content="do the work",
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(model.requests) == 1
    assert [message.role for message in model.requests[0].messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
    ]


def test_gateway_fails_closed_when_required_binding_is_missing(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "MODEL_GATEWAY_API_KEY",
        "internal-test-token",
    )

    model = CapturingModel()
    bindings = InMemoryRunContextBindings()
    session_id = "11111111-1111-1111-1111-111111111111"

    bindings.require(UUID(session_id))
    install_dependencies(
        model=model,
        bindings=bindings,
    )

    try:
        response = post_completion(
            TestClient(app),
            session_id=session_id,
            user_content="do the work",
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["type"] == ("required_context_binding_missing")
    assert model.requests == []


def test_gateway_reuses_binding_without_accumulating_context(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "MODEL_GATEWAY_API_KEY",
        "internal-test-token",
    )

    model = CapturingModel()
    bindings = InMemoryRunContextBindings()
    session_id = "11111111-1111-1111-1111-111111111111"
    run_id = UUID(session_id)
    context_text = "stable reference context"

    bindings.bind(
        run_id,
        make_prepared_context(context_text),
    )
    install_dependencies(
        model=model,
        bindings=bindings,
    )

    try:
        client = TestClient(app)

        first = post_completion(
            client,
            session_id=session_id,
            user_content="first model turn",
        )
        second = post_completion(
            client,
            session_id=session_id,
            user_content="second model turn",
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(model.requests) == 2

    for request in model.requests:
        context_messages = [
            message for message in request.messages if message.content == context_text
        ]
        assert len(context_messages) == 1
        assert context_messages[0].role is MessageRole.USER

    assert bindings.resolve(run_id) is not None
