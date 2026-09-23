import os
from collections.abc import Mapping
from pathlib import Path

from agent_platform.adapters.run_history.sqlite import (
    SQLiteRunHistoryStore,
)


def build_run_history(
    env: Mapping[str, str] | None = None,
) -> (
    tuple[
        SQLiteRunHistoryStore,
        str,
        str | None,
    ]
    | None
):
    """Compose optional persistent run history from deployment configuration."""

    values = os.environ if env is None else env

    database_path = values.get(
        "AGENT_PLATFORM_RUN_HISTORY_DB",
        "",
    ).strip()
    platform_revision = values.get(
        "AGENT_PLATFORM_PLATFORM_REVISION",
        "",
    ).strip()
    repository_revision = values.get(
        "AGENT_PLATFORM_REPOSITORY_REVISION",
        "",
    ).strip()

    if not database_path:
        if platform_revision or repository_revision:
            raise ValueError("Run history revisions require AGENT_PLATFORM_RUN_HISTORY_DB.")

        return None

    if not platform_revision:
        raise ValueError(
            "AGENT_PLATFORM_PLATFORM_REVISION is required when run history is enabled."
        )

    store = SQLiteRunHistoryStore(
        Path(database_path),
    )

    return (
        store,
        platform_revision,
        repository_revision or None,
    )
