from typing import Protocol
from uuid import UUID

from agent_platform.domain.run_history import (
    ModelInvocationRecord,
    RunHistoryCompletion,
    RunHistoryRecord,
    RunHistoryStart,
    ToolInvocationRecord,
)


class RunHistoryStoreContract(Protocol):
    def start_run(
        self,
        record: RunHistoryStart,
    ) -> None: ...

    def finish_run(
        self,
        completion: RunHistoryCompletion,
    ) -> None: ...

    def append_model_invocation(
        self,
        record: ModelInvocationRecord,
    ) -> None: ...

    def append_tool_invocation(
        self,
        record: ToolInvocationRecord,
    ) -> None: ...

    def get(
        self,
        run_id: UUID,
    ) -> RunHistoryRecord | None: ...

    def list_recent(
        self,
        *,
        limit: int = 50,
    ) -> tuple[RunHistoryRecord, ...]: ...
