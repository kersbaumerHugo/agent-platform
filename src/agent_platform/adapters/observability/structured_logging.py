import json
import logging

from agent_platform.domain.observability import (
    ObservationEvent,
    ObservationStatus,
)


class StructuredLogObserver:
    def __init__(
        self,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or self._build_logger()

    @staticmethod
    def _build_logger() -> logging.Logger:
        logger = logging.getLogger("agent_platform.telemetry")
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)

        logger.propagate = False
        return logger

    def record(self, event: ObservationEvent) -> None:
        payload = event.model_dump(
            mode="json",
            exclude_none=True,
        )

        message = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        )

        if event.status == ObservationStatus.FAILED:
            self._logger.error(message)
        else:
            self._logger.info(message)
