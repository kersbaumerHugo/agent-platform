import os
import shutil
from collections.abc import Mapping
from pathlib import Path

from agent_platform.adapters.capabilities.repository import (
    RepositoryInspectionCapability,
)
from agent_platform.adapters.memory.context_provider import (
    MemoryContextProvider,
)
from agent_platform.adapters.memory.sqlite import SQLiteFTSRetrieval
from agent_platform.adapters.models.local_openai import (
    LocalOpenAIModelAdapter,
)
from agent_platform.adapters.models.openrouter import (
    OpenRouterModelAdapter,
)
from agent_platform.adapters.observability.default import (
    default_observer,
)
from agent_platform.adapters.repository.repowise import (
    RepoWiseRepositoryBackend,
)
from agent_platform.adapters.repository.repowise_mcp import (
    RepoWiseMCPClient,
)
from agent_platform.adapters.runtimes.dsh import DSHRuntime
from agent_platform.adapters.runtimes.fake import FakeRuntime
from agent_platform.adapters.runtimes.tool_calling import (
    ToolCallingRuntime,
)
from agent_platform.adapters.tools.repository import (
    RepositoryInspectionTool,
)
from agent_platform.application.capability_authorization import (
    StaticCapabilityAuthorizationPolicy,
)
from agent_platform.application.context_assembler import (
    DeterministicContextAssembler,
)
from agent_platform.application.context_budget import (
    DeterministicContextBudgetPolicy,
    Utf8ByteTokenEstimator,
)
from agent_platform.application.context_injector import (
    ReferenceMessageInjector,
)
from agent_platform.application.context_preparation import PrepareContext
from agent_platform.application.context_renderer import (
    MarkdownContextRenderer,
)
from agent_platform.application.context_trace import ContextTraceBuilder
from agent_platform.application.model_gateway import ModelGateway
from agent_platform.application.recall_planner import (
    DeterministicRecallPlanner,
)
from agent_platform.application.retrieval_acceptance import (
    LexicalRetrievalAcceptanceGate,
)
from agent_platform.application.tool_registry import ToolRegistry
from agent_platform.contracts.observability import ObservationContract
from agent_platform.contracts.runtime import RuntimeContract
from agent_platform.domain.context_budget import ContextBudget

AGENT_RUNTIME_PRINCIPAL = "system:agent-runtime"


def build_agent_tool_registry(
    env: Mapping[str, str] | None = None,
    *,
    observer: ObservationContract = default_observer,
) -> ToolRegistry:
    values = os.environ if env is None else env

    repository_path = values.get(
        "AGENT_PLATFORM_REPOSITORY_PATH",
        "",
    ).strip()

    if not repository_path:
        raise ValueError("AGENT_PLATFORM_REPOSITORY_PATH is not configured.")

    repository = Path(repository_path)

    if not repository.is_dir():
        raise ValueError(
            f"AGENT_PLATFORM_REPOSITORY_PATH must reference an existing directory: {repository}"
        )

    repowise_command = values.get(
        "AGENT_PLATFORM_REPOWISE_COMMAND",
        "repowise",
    ).strip()

    if not repowise_command:
        raise ValueError("AGENT_PLATFORM_REPOWISE_COMMAND must not be blank.")

    resolved_repowise = shutil.which(repowise_command)

    if resolved_repowise is None:
        raise ValueError(
            f"AGENT_PLATFORM_REPOWISE_COMMAND could not be resolved: {repowise_command}"
        )

    repowise_client = RepoWiseMCPClient(
        repository_path=repository,
        command=resolved_repowise,
    )

    repository_backend = RepoWiseRepositoryBackend(
        repowise_client,
    )

    repository_capability = RepositoryInspectionCapability(
        repository_backend,
    )

    authorization = StaticCapabilityAuthorizationPolicy(
        grants=[
            (
                AGENT_RUNTIME_PRINCIPAL,
                "repository.inspect",
            )
        ]
    )

    repository_tool = RepositoryInspectionTool(
        repository_capability,
        authorization,
    )

    return ToolRegistry(
        [repository_tool],
        observer,
    )


def build_model_gateway(
    env: Mapping[str, str] | None = None,
    *,
    observer: ObservationContract = default_observer,
) -> ModelGateway:
    values = os.environ if env is None else env

    provider = (
        values.get(
            "MODEL_PROVIDER",
            "openrouter",
        )
        .strip()
        .lower()
    )

    if provider == "openrouter":
        api_key = values.get(
            "OPENROUTER_API_KEY",
            "",
        ).strip()

        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not configured.")

        model = values.get(
            "OPENROUTER_MODEL",
            "openrouter/free",
        ).strip()

        if not model:
            raise ValueError("OPENROUTER_MODEL must not be blank.")

        return ModelGateway(
            OpenRouterModelAdapter(
                api_key=api_key,
                model=model,
                timeout_seconds=90.0,
            ),
            observer=observer,
        )

    if provider == "local":
        api_key = values.get(
            "LOCAL_MODEL_API_KEY",
            "",
        ).strip()
        base_url = values.get(
            "LOCAL_MODEL_BASE_URL",
            "",
        ).strip()
        model = values.get(
            "LOCAL_MODEL_NAME",
            "",
        ).strip()

        if not api_key:
            raise ValueError("LOCAL_MODEL_API_KEY is not configured.")

        if not base_url:
            raise ValueError("LOCAL_MODEL_BASE_URL is not configured.")

        if not model:
            raise ValueError("LOCAL_MODEL_NAME is not configured.")

        timeout_text = values.get(
            "LOCAL_MODEL_TIMEOUT_SECONDS",
            "90",
        ).strip()

        try:
            timeout_seconds = float(timeout_text)
        except ValueError as exc:
            raise ValueError("LOCAL_MODEL_TIMEOUT_SECONDS must be a number.") from exc

        if timeout_seconds <= 0:
            raise ValueError("LOCAL_MODEL_TIMEOUT_SECONDS must be greater than 0.")

        return ModelGateway(
            LocalOpenAIModelAdapter(
                api_key=api_key,
                model=model,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                enable_thinking=False,
            ),
            observer=observer,
        )

    raise ValueError(f"Unsupported MODEL_PROVIDER: {provider}")


def build_runtime(
    env: Mapping[str, str] | None = None,
) -> RuntimeContract:
    values = os.environ if env is None else env
    runtime_name = (
        values.get(
            "AGENT_PLATFORM_RUNTIME",
            "fake",
        )
        .strip()
        .lower()
    )

    if runtime_name == "fake":
        return FakeRuntime()

    if runtime_name == "dsh":
        return _build_dsh_runtime(values)

    if runtime_name == "tool-calling":
        return _build_tool_calling_runtime(values)

    raise ValueError(
        f"Unsupported AGENT_PLATFORM_RUNTIME {runtime_name!r}; "
        "expected 'fake', 'dsh', or 'tool-calling'."
    )


def _build_tool_calling_runtime(
    env: Mapping[str, str],
) -> ToolCallingRuntime:
    gateway = build_model_gateway(env)
    registry = build_agent_tool_registry(env)

    return ToolCallingRuntime(
        gateway=gateway,
        registry=registry,
        principal_id=AGENT_RUNTIME_PRINCIPAL,
    )


def build_context_preparation(
    env: Mapping[str, str] | None = None,
) -> tuple[PrepareContext, ContextBudget] | None:
    values = os.environ if env is None else env
    database_path = values.get(
        "AGENT_PLATFORM_MEMORY_DB",
        "",
    ).strip()

    if not database_path:
        return None

    max_total_tokens = _configured_int(
        values,
        "AGENT_PLATFORM_CONTEXT_MAX_TOTAL_TOKENS",
        default=4096,
        minimum=1,
    )
    base_input_tokens = _configured_int(
        values,
        "AGENT_PLATFORM_CONTEXT_BASE_INPUT_TOKENS",
        default=0,
        minimum=0,
    )
    reserved_output_tokens = _configured_int(
        values,
        "AGENT_PLATFORM_CONTEXT_RESERVED_OUTPUT_TOKENS",
        default=1024,
        minimum=0,
    )

    retrieval = SQLiteFTSRetrieval(
        Path(database_path),
    )
    acceptance = LexicalRetrievalAcceptanceGate()
    provider = MemoryContextProvider(
        retrieval=retrieval,
        acceptance=acceptance,
    )
    estimator = Utf8ByteTokenEstimator()

    prepare_context = PrepareContext(
        planner=DeterministicRecallPlanner(),
        provider=provider,
        assembler=DeterministicContextAssembler(),
        budget_policy=DeterministicContextBudgetPolicy(
            estimator=estimator,
        ),
        token_estimator=estimator,
        renderer=MarkdownContextRenderer(),
        injector=ReferenceMessageInjector(),
        trace_builder=ContextTraceBuilder(),
    )
    budget = ContextBudget(
        max_total_tokens=max_total_tokens,
        base_input_tokens=base_input_tokens,
        reserved_output_tokens=reserved_output_tokens,
    )

    return prepare_context, budget


def _configured_int(
    env: Mapping[str, str],
    name: str,
    *,
    default: int,
    minimum: int,
) -> int:
    raw_value = env.get(name, str(default)).strip()

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc

    if value < minimum:
        raise ValueError(f"{name} must be greater than or equal to {minimum}.")

    return value


def _build_dsh_runtime(
    env: Mapping[str, str],
) -> DSHRuntime:
    provider = _required(
        env,
        "AGENT_PLATFORM_DSH_PROVIDER",
    )
    model = _required(
        env,
        "AGENT_PLATFORM_DSH_MODEL",
    )

    dsh_home = Path(
        env.get(
            "AGENT_PLATFORM_DSH_HOME",
            ".runtime/dsh",
        )
    )
    cwd = Path(
        env.get(
            "AGENT_PLATFORM_DSH_CWD",
            ".",
        )
    )
    profile = env.get(
        "AGENT_PLATFORM_DSH_PROFILE",
        "sdk",
    ).strip()

    timeout_text = env.get(
        "AGENT_PLATFORM_DSH_TIMEOUT_SECONDS",
        "120",
    ).strip()

    try:
        timeout_seconds = float(timeout_text)
    except ValueError as exc:
        raise ValueError("AGENT_PLATFORM_DSH_TIMEOUT_SECONDS must be a number.") from exc

    if timeout_seconds <= 0:
        raise ValueError("AGENT_PLATFORM_DSH_TIMEOUT_SECONDS must be greater than 0.")

    patches = tuple(
        Path(value.strip())
        for value in env.get(
            "AGENT_PLATFORM_DSH_PATCHES",
            "",
        ).split(",")
        if value.strip()
    )

    return DSHRuntime(
        dsh_home=dsh_home,
        cwd=cwd,
        provider=provider,
        model=model,
        profile=profile,
        request_timeout_seconds=timeout_seconds,
        patches=patches,
    )


def _required(
    env: Mapping[str, str],
    name: str,
) -> str:
    value = env.get(name, "").strip()

    if not value:
        raise ValueError(f"{name} is required when AGENT_PLATFORM_RUNTIME=dsh.")

    return value
