from prometheus_client import Counter, Histogram

from agent_platform.domain.observability import (
    ObservationComponent,
    ObservationEvent,
    ObservationStatus,
)

RUNS = Counter(
    "agent_platform_runs_total",
    "Completed agent platform runs.",
    ["runtime", "status"],
)

RUN_DURATION = Histogram(
    "agent_platform_run_duration_seconds",
    "Agent platform run duration.",
    ["runtime"],
)

MODEL_REQUESTS = Counter(
    "agent_platform_model_requests_total",
    "Completed model requests.",
    ["provider", "model", "status"],
)

MODEL_DURATION = Histogram(
    "agent_platform_model_request_duration_seconds",
    "Model request duration.",
    ["provider", "model"],
)

MODEL_TOKENS = Counter(
    "agent_platform_model_tokens_total",
    "Model token usage.",
    ["provider", "model", "token_type"],
)

TOOL_REQUESTS = Counter(
    "agent_platform_tool_requests_total",
    "Completed tool requests.",
    ["tool", "status"],
)

TOOL_DURATION = Histogram(
    "agent_platform_tool_request_duration_seconds",
    "Tool request duration.",
    ["tool"],
)


class PrometheusObserver:
    def record(self, event: ObservationEvent) -> None:
        if event.component == ObservationComponent.RUN:
            self._record_run(event)

        elif event.component == ObservationComponent.TOOL:
            self._record_tool(event)

    @staticmethod
    def _record_run(event: ObservationEvent) -> None:
        if event.status == ObservationStatus.STARTED:
            return

        runtime = event.runtime or "unknown"

        RUNS.labels(
            runtime=runtime,
            status=event.status.value,
        ).inc()

        if event.duration_seconds is not None:
            RUN_DURATION.labels(runtime=runtime).observe(event.duration_seconds)

    @staticmethod
    def _record_model(event: ObservationEvent) -> None:
        if event.status == ObservationStatus.STARTED:
            return

        provider = event.provider or "unknown"
        model = event.model or "unknown"

        MODEL_REQUESTS.labels(
            provider=provider,
            model=model,
            status=event.status.value,
        ).inc()

        if event.duration_seconds is not None:
            MODEL_DURATION.labels(
                provider=provider,
                model=model,
            ).observe(event.duration_seconds)

        if event.status != ObservationStatus.SUCCEEDED:
            return

        token_values = {
            "prompt": event.prompt_tokens,
            "completion": event.completion_tokens,
            "total": event.total_tokens,
        }

        for token_type, value in token_values.items():
            if value is not None:
                MODEL_TOKENS.labels(
                    provider=provider,
                    model=model,
                    token_type=token_type,
                ).inc(value)

    @staticmethod
    def _record_tool(event: ObservationEvent) -> None:
        if event.status == ObservationStatus.STARTED:
            return

        tool_name = event.tool_name or "unknown"

        TOOL_REQUESTS.labels(
            tool=tool_name,
            status=event.status.value,
        ).inc()

        if event.duration_seconds is not None:
            TOOL_DURATION.labels(
                tool=tool_name,
            ).observe(event.duration_seconds)
