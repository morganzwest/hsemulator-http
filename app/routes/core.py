"""
Core application endpoints.

This blueprint contains the fundamental endpoints for the application
including health checks and action execution.
"""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.requests import Request

from app.models import HealthResponse, ExecuteRequest, ExecuteAcceptedResponse
from app.db import get_supabase
from app.services.execution_service import enqueue_execution_job
from app.config import settings
from app.workers.base import run_execution

router = APIRouter(
    tags=["Core Operations"],
    responses={
        500: {"description": "Internal server error", "model": dict},
        404: {"description": "Resource not found", "model": dict}
    }
)


@router.get(
    "/health", 
    response_model=HealthResponse,
    summary="Health Check",
    description="""
    Health check endpoint for monitoring service status.
    
    This endpoint verifies that the service and its dependencies are functioning
    correctly by testing database connectivity. It returns service metadata
    including status, name, and environment.
    
    **Use Cases:**
    - Load balancer health checks
    - Monitoring system integration
    - Service availability verification
    
    **Returns:**
    - 200: Service is healthy and operational
    - 500: Service or database connectivity issues
    """,
    responses={
        200: {
            "description": "Service is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "service": "novocode-runtime",
                        "environment": "development"
                    }
                }
            }
        },
        500: {"description": "Service unavailable or database connectivity issues"}
    }
)
def health_check():
    """
    Health check endpoint for monitoring service status.

    This endpoint verifies that the service and its dependencies are functioning
    correctly by testing database connectivity. It returns service metadata
    including status, name, and environment.

    Returns:
        HealthResponse: Service health status and metadata
    """
    # Test database connectivity with a lightweight query
    supabase = get_supabase()
    supabase.table("action_executions").select("id").limit(1).execute()

    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
    )


@router.post(
    "/execute",
    summary="Execute Workflow Action",
    description="""
    Execute a HubSpot workflow action.
    
    This endpoint queues a workflow action for execution. In local mode,
    it executes immediately. In cloud mode, it queues the job for
    asynchronous processing by the job scheduler.
    
    **Execution Modes:**
    - **Local**: Immediate execution (development/testing)
    - **Cloud**: Queued for async processing (production)
    
    **Use Cases:**
    - Triggering custom code actions in HubSpot workflows
    - Processing webhook data
    - Integrating with external systems
    
    **Flow:**
    1. Validate execution request
    2. Queue job for processing
    3. Return execution ID for tracking
    4. Process job asynchronously or immediately
    """,
    responses={
        200: {
            "description": "Action execution queued successfully",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "execution_id": "550e8400-e29b-41d4-a716-446655440000",
                        "status": "queued"
                    }
                }
            }
        },
        400: {"description": "Invalid execution request"},
        500: {"description": "Internal server error during execution"}
    }
)
async def execute(req: ExecuteRequest):
    """
    Execute a HubSpot workflow action.

    This endpoint queues a workflow action for execution. In local mode,
    it executes immediately. In cloud mode, it queues the job for
    asynchronous processing by the job scheduler.

    Args:
        req: Execution request containing action configuration and execution ID

    Returns:
        ExecuteAcceptedResponse: Confirmation of job queuing with execution status
    """
    payload = req.model_dump(mode="json")

    # Queue the execution job for processing
    await enqueue_execution_job(req.execution_id, payload)

    # In local mode, execute immediately (for development/testing)
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
