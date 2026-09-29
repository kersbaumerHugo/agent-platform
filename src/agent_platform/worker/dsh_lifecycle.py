from __future__ import annotations

import json
import sys
from collections.abc import Callable
from time import monotonic


def lifecycle_observer() -> Callable[[object], None]:
    """Emit only safe DSH lifecycle metadata to stderr."""

    started_at = monotonic()

    def observe(notification: object) -> None:
        method = getattr(
            notification,
            "method",
            None,
        )

        payload = getattr(
            notification,
            "payload",
            None,
        )

        if not isinstance(method, str):
            return

        if not isinstance(payload, dict):
            return

        record: dict[str, object] = {
            "elapsed_seconds": round(
                monotonic() - started_at,
                3,
            ),
            "method": method,
        }

        if method == "session.status":
            status = payload.get("status")

            if isinstance(status, str):
                record["status"] = status

        if method == "session.event":
            event = payload.get("event")

            if isinstance(event, dict):
                event_type = event.get("type")

                if isinstance(event_type, str):
                    record["event_type"] = event_type

        print(
            "DSH_LIFECYCLE "
            + json.dumps(
                record,
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )

    return observe
