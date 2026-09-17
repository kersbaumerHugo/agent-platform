import os
from collections.abc import Mapping
from pathlib import Path

from agent_platform.adapters.runtimes.dsh import DSHRuntime
from agent_platform.adapters.runtimes.fake import FakeRuntime
from agent_platform.contracts.runtime import RuntimeContract


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

    raise ValueError(
        f"Unsupported AGENT_PLATFORM_RUNTIME {runtime_name!r}; expected 'fake' or 'dsh'."
    )


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
