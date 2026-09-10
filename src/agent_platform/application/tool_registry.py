from collections.abc import Iterable
from time import perf_counter

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, Tracer

from agent_platform.contracts.observability import (
    ObservationContract,
)
from agent_platform.contracts.tool import ToolContract
from agent_platform.domain.observability import (
    ObservationComponent,
    ObservationEvent,
    ObservationStatus,
)
from agent_platform.domain.tool import (
    ToolDefinition,
    ToolRequest,
    ToolResult,
)


class ToolRegistry:
    def __init__(
        self,
        tools: Iterable[ToolContract],
        observer: ObservationContract,
        tracer: Tracer | None = None,
    ) -> None:
        self._tools: dict[str, ToolContract] = {}
        self._observer = observer
        self._tracer = tracer or trace.get_tracer("agent_platform.tool_registry")

        for tool in tools:
            self.register(tool)

    def register(
        self,
        tool: ToolContract,
    ) -> None:
        name = tool.definition.name

        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")

        self._tools[name] = tool

    def definitions(self) -> list[ToolDefinition]:
        return [self._tools[name].definition for name in sorted(self._tools)]

    async def invoke(
        self,
        name: str,
        request: ToolRequest,
    ) -> ToolResult:
        try:
            tool = self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

        started = perf_counter()

        with self._tracer.start_as_current_span("tool.invoke") as span:
            span.set_attribute(
                "agent_platform.run.id",
                str(request.run_id),
            )
            span.set_attribute(
                "agent_platform.tool.name",
                name,
            )

            self._observer.record(
                ObservationEvent(
                    run_id=request.run_id,
                    component=ObservationComponent.TOOL,
                    event="tool.request.started",
                    status=ObservationStatus.STARTED,
                    tool_name=name,
                )
            )

            try:
                result = await tool.invoke(request)

                if result.run_id != request.run_id:
                    raise RuntimeError("Tool returned a mismatched run_id.")

                if result.tool_name != name:
                    raise RuntimeError("Tool returned a mismatched tool name.")

            except Exception as exc:
                duration = perf_counter() - started

                span.set_attribute(
                    "error.type",
                    type(exc).__name__,
                )
                span.record_exception(exc)
                span.set_status(
                    Status(
                        StatusCode.ERROR,
                        type(exc).__name__,
                    )
                )

                self._observer.record(
                    ObservationEvent(
                        run_id=request.run_id,
                        component=ObservationComponent.TOOL,
                        event="tool.request.failed",
                        status=ObservationStatus.FAILED,
                        tool_name=name,
                        duration_seconds=duration,
                        error_type=type(exc).__name__,
                    )
                )

                raise

            duration = perf_counter() - started

            span.set_attribute(
                "agent_platform.tool.status",
                "succeeded",
            )
            span.set_status(Status(StatusCode.OK))

            self._observer.record(
                ObservationEvent(
                    run_id=request.run_id,
                    component=ObservationComponent.TOOL,
                    event="tool.request.succeeded",
                    status=ObservationStatus.SUCCEEDED,
                    tool_name=name,
                    duration_seconds=duration,
                )
            )

            return result
