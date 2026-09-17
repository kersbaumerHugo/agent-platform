import logging

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from agent_platform.adapters.observability.default import default_observer
from agent_platform.adapters.observability.tracing import configure_tracing
from agent_platform.api.composition import build_runtime
from agent_platform.api.openai_compat import router as openai_compat_router
from agent_platform.application.run_agent import RunAgent
from agent_platform.application.run_context import (
    default_run_context_bindings,
)
from agent_platform.application.work_orchestrator import WorkOrchestrator
from agent_platform.domain.models import RunRequest, RunResult
from agent_platform.domain.work import WorkRequest, WorkResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
configure_tracing()

app = FastAPI(title="Agent Platform", version="0.0.1")
app.include_router(openai_compat_router)

runtime = build_runtime()

service = RunAgent(
    runtime=runtime,
    observer=default_observer,
    run_context_bindings=default_run_context_bindings,
)
work_service = WorkOrchestrator(
    run_agent=service,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs", response_model=RunResult)
async def create_run(request: RunRequest) -> RunResult:
    return await service.execute(request)


@app.post("/work", response_model=WorkResult)
async def create_work(request: WorkRequest) -> WorkResult:
    return await work_service.execute(request)


@app.get("/metrics")
async def metrics() -> Response:
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
