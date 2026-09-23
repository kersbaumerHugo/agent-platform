from agent_platform.contracts.run_history import (
    RunHistoryStoreContract,
)
from agent_platform.domain.observability import (
    ObservationComponent,
    ObservationEvent,
    ObservationStatus,
)
from agent_platform.domain.run_history import (
    ModelInvocationRecord,
    ToolInvocationRecord,
)


class RunHistoryObserver:
    """Persist terminal model/tool evidence for already-started runs."""

    def __init__(
        self,
        store: RunHistoryStoreContract,
    ) -> None:
        self._store = store

    def record(
        self,
        event: ObservationEvent,
    ) -> None:
        if event.status == ObservationStatus.STARTED:
            return

        if event.component == ObservationComponent.MODEL_GATEWAY:
            self._record_model(event)
            return

        if event.component == ObservationComponent.TOOL:
            self._record_tool(event)

    def _record_model(
        self,
        event: ObservationEvent,
    ) -> None:
        if event.provider is None or not event.provider.strip():
            raise ValueError("Terminal model observation requires provider.")

        if event.model is None or not event.model.strip():
            raise ValueError("Terminal model observation requires requested model.")

        self._store.append_model_invocation(
            ModelInvocationRecord(
                run_id=event.run_id,
                provider=event.provider,
                requested_model=event.model,
                resolved_model=event.resolved_model,
                status=event.status,
                observed_at=event.observed_at,
                duration_seconds=event.duration_seconds,
                prompt_tokens=event.prompt_tokens,
                completion_tokens=event.completion_tokens,
                total_tokens=event.total_tokens,
                error_type=event.error_type,
            )
        )

    def _record_tool(
        self,
        event: ObservationEvent,
    ) -> None:
        if event.tool_name is None or not event.tool_name.strip():
            raise ValueError("Terminal tool observation requires tool name.")

        self._store.append_tool_invocation(
            ToolInvocationRecord(
                run_id=event.run_id,
                tool_name=event.tool_name,
                status=event.status,
                observed_at=event.observed_at,
                duration_seconds=event.duration_seconds,
                error_type=event.error_type,
            )
        )
