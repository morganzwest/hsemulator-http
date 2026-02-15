from __future__ import annotations
from fastapi import Response

import asyncio
import logging
from uuid import UUID

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request

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
    DeleteSecretResponse,
    DeleteSecretRequest
)
from app.models.cicd import (
    CicdPromoteRequest,
    CicdPromoteResponse
)

from app.services.secret_service import create_secret, update_secret, delete_secret
from app.services.secret_decrypt_service import decrypt_secret_for_test
from app.services.cicd_service import (
    promote_to_hubspot,
    CICDServiceError,
    SecretDecryptionError,
    ActionNotManagedError,
    NoUpdateNeededError
)
from app.workers.base import run_execution
from app.models.errors import (
    SecretPersistenceError,
    SecretPortalMismatchError,
    SecretForbiddenError,
    SecretNotFoundError
)
from os import getenv

IS_CLOUD_RUN = bool(getenv("K_SERVICE"))

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
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ----------------------------
# Routes
# ----------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc)},
    )


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
        # NOTE: Long term, this should be enabled.
        # if IS_CLOUD_RUN:
        #     raise RuntimeError(
        #         "Local execution mode is not allowed in Cloud Run")
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


@app.post(
    "/cicd/promote",
    response_model=CicdPromoteResponse,
    dependencies=[Depends(require_runtime_token)],
)
async def cicd_promote(req: CicdPromoteRequest, force: bool = False, dry_run: bool = False):
    """
    Promote source code to a HubSpot workflow action.
    
    This endpoint allows CI/CD systems to update HubSpot workflow actions
    by providing source code and a CICD secret ID (containing the HubSpot token).
    
    Args:
        req: Promotion request with source code, secret ID, workflow ID, and search key
        force: Force update even if action has no hash marker (default: False)
        dry_run: Perform dry run without making changes (default: False)
    """
    try:
        result = await promote_to_hubspot(
            source_code=req.source_code,
            cicd_secret_id=req.cicd_secret_id,
            workflow_id=req.workflow_id,
            search_key=req.search_key,
            force=force,
            dry_run=dry_run,
        )
        
        return CicdPromoteResponse(
            ok=result["ok"],
            workflow_id=result["workflow_id"],
            new_hash=result["new_hash"],
            revision_id=result.get("revision_id"),
            action_index=result.get("action_index"),
        )
        
    except NoUpdateNeededError as e:
        # Return success response for no-op updates
        return CicdPromoteResponse(
            ok=True,
            workflow_id=req.workflow_id,
            new_hash=str(e).split(" ")[-1],  # Extract hash from error message
            revision_id=None,
            action_index=None,
        )
        
    except (SecretDecryptionError, ActionNotManagedError) as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    except CICDServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    except Exception as e:
        logger.exception("Unexpected error in CICD promote")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.delete(
    "/secrets/{secret_id}",
    response_model=DeleteSecretResponse,
    dependencies=[Depends(require_runtime_token)]
)
def delete_secret_endpoint(secret_id: UUID, req: DeleteSecretRequest):
    try:
        delete_secret(
            secret_id=secret_id,
            portal_id=req.portal_id,
            user_id=req.user_id
        )
        return DeleteSecretResponse(ok=True, secret_id=secret_id)

    except (SecretNotFoundError, SecretPortalMismatchError, SecretForbiddenError) as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    except SecretPersistenceError as e:
        raise e
