import logging
from uuid import UUID

from prometheus_client import Counter, Histogram

logger = logging.getLogger("agent_platform")

RUNS = Counter(
    "agent_platform_runs_total",
    "Agent platform runs.",
    ["runtime", "status"],
)

DURATION = Histogram(
    "agent_platform_run_duration_seconds",
    "Agent platform run duration.",
    ["runtime"],
)


class PrometheusObserver:
    def run_started(self, run_id: UUID, runtime: str) -> None:
        logger.info(
            "run_started run_id=%s runtime=%s",
            run_id,
            runtime,
        )

    def run_succeeded(self, run_id: UUID, runtime: str, duration_seconds: float) -> None:
        RUNS.labels(runtime=runtime, status="succeeded").inc()
        DURATION.labels(runtime=runtime).observe(duration_seconds)
        logger.info(
            "run_succeeded run_id=%s runtime=%s duration_seconds=%f",
            run_id,
            runtime,
            duration_seconds,
        )

    def run_failed(self, run_id: UUID, runtime: str, duration_seconds: float) -> None:
        RUNS.labels(runtime=runtime, status="failed").inc()
        DURATION.labels(runtime=runtime).observe(duration_seconds)
        logger.exception(
            "run_failed run_id=%s runtime=%s duration_seconds=%f",
            run_id,
            runtime,
            duration_seconds,
        )
