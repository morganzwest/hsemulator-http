from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models import HealthResponse, ExecuteRequest, ExecuteAcceptedResponse
from app.db import get_supabase
from app.services.execution_service import enqueue_execution_job
from app.logger import ExecutionContextFilter
from app.auth import require_runtime_token
from app.models.secrets import (
    CreateSecretRequest,
    CreateSecretResponse,
    UpdateSecretRequest,
    UpdateSecretResponse,
)
from app.services.secret_service import create_secret, update_secret
from app.services.secret_decrypt_service import decrypt_secret_for_test
from app.workers.base import run_execution


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

logging.basicConfig(level=logging.INFO, handlers=[handler])

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

# ----------------------------
# CORS
# ----------------------------
# Prefer a list from config, e.g.:
# CORS_ORIGINS="http://localhost:3000,https://app.example.com"
origins = (
    settings.cors_origins
    if isinstance(settings.cors_origins, list)
    else [o.strip() for o in settings.cors_origins.split(",")]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,          # DO NOT use ["*"] with credentials
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ----------------------------
# Routes
# ----------------------------


@app.get("/health", response_model=HealthResponse)
def health_check():
    supabase = get_supabase()
    supabase.table("action_executions").select("id").limit(1).execute()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
    )


@app.post("/execute")
async def execute(req: ExecuteRequest):
    payload = req.model_dump(mode="json")
    await enqueue_execution_job(req.execution_id, payload)

    if settings.execution_mode == "local":
        await run_execution(req.execution_id)

    return ExecuteAcceptedResponse(
        ok=True,
        execution_id=req.execution_id,
        status="queued",
    )


@app.post(
    "/secrets",
    response_model=CreateSecretResponse,
    dependencies=[Depends(require_runtime_token)],
)
def create_secret_endpoint(req: CreateSecretRequest):
    secret_id = create_secret(
        scope=req.scope,
        portal_id=req.portal_id,
        action_id=req.action_id,
        name=req.name,
        value=req.value,
        created_by=req.created_by,
    )
    return CreateSecretResponse(ok=True, secret_id=secret_id)


@app.put(
    "/secrets/{secret_id}",
    response_model=UpdateSecretResponse,
    dependencies=[Depends(require_runtime_token)],
)
def update_secret_endpoint(secret_id: UUID, req: UpdateSecretRequest):
    update_secret(secret_id=secret_id, value=req.value)
    return UpdateSecretResponse(ok=True, secret_id=secret_id)
