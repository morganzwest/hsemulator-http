from __future__ import annotations

import asyncio
from fastapi import FastAPI, Depends

from app.config import settings
from app.models import HealthResponse, ExecuteRequest, ExecuteAcceptedResponse
from app.db import get_supabase
from app.services.execution_service import enqueue_execution_job
from app.workers.base import worker_loop
import logging
from app.logging import ExecutionContextFilter
from app.auth import require_runtime_token

handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s "
        "execution_id=%(execution_id)s "
        "status=%(status)s "
        "%(message)s"
    )
)

handler.addFilter(ExecutionContextFilter())

logging.basicConfig(
    level=logging.INFO,
    handlers=[handler],
)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)


@app.on_event("startup")
async def on_startup():
    # Start a single in-process worker for now.
    # Later you’ll run dedicated worker processes instead.
    asyncio.create_task(worker_loop())


@app.get("/health", response_model=HealthResponse)
def health_check():
    supabase = get_supabase()
    supabase.table("action_executions").select("id").limit(1).execute()

    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
    )


@app.post("/execute", response_model=ExecuteAcceptedResponse, dependencies=[Depends(require_runtime_token)])
async def execute(req: ExecuteRequest):
    # enqueue job + update status in DB
    await enqueue_execution_job(req.execution_id, req.model_dump())

    return ExecuteAcceptedResponse(
        ok=True,
        execution_id=req.execution_id,
        status="queued",
    )
