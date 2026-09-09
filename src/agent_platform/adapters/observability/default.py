from agent_platform.adapters.observability.composite import (
    CompositeObserver,
)
from agent_platform.adapters.observability.prometheus import (
    PrometheusObserver,
)
from agent_platform.adapters.observability.structured_logging import (
    StructuredLogObserver,
)

default_observer = CompositeObserver(
    (
        PrometheusObserver(),
        StructuredLogObserver(),
    )
)
