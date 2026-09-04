import logging

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from agent_platform.adapters.observability.prometheus import PrometheusObserver
from agent_platform.adapters.runtimes.fake import FakeRuntime
from agent_platform.application.run_agent import RunAgent
from agent_platform.domain.models import RunRequest, RunResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="Agent Platform", version="0.0.1")

service = RunAgent(
    runtime=FakeRuntime(),
    observer=PrometheusObserver(),
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs", response_model=RunResult)
async def create_run(request: RunRequest) -> RunResult:
    return await service.execute(request)


@app.get("/metrics")
async def metrics() -> Response:
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
