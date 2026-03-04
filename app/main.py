"""
Novocode Runtime API - Main FastAPI Application

This module provides the main HTTP API for the Novocode service, which handles
workflow action execution, secret management, and CI/CD operations.

Key Features:
- Workflow action execution with local and cloud modes
- Secure secret storage and retrieval with AES-GCM encryption
- CI/CD integration for HubSpot workflow management
- Comprehensive error tracking with Sentry integration
- Authentication via runtime API tokens

Architecture:
- FastAPI-based REST API with CORS support
- Asynchronous execution with job queuing
- Layered authentication and authorization
- Structured error handling and logging

Environment Variables:
- EXECUTION_MODE: 'local' for immediate execution, 'cloud' for job queuing
- RUNTIME_API_TOKEN: Bearer token for API authentication
- SENTRY_DSN: Error tracking configuration
- CORS_ORIGINS: Comma-separated list of allowed origins
"""

from __future__ import annotations
from fastapi import Response

import asyncio
import logging
from uuid import UUID
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request

from app.config import settings
from app.models import HealthResponse, ExecuteRequest, ExecuteAcceptedResponse
from app.db import get_supabase
from app.services.execution_service import enqueue_execution_job
from app.logger import ExecutionContextFilter, SentryContextFilter
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
    CicdPromoteByUrlRequest,
    CicdPromoteResponse,
    WorkflowStatusResponse,
    GetWorkflowActionsRequest,
    GetWorkflowActionsResponse,
)
from app.models.workflows import (
    WorkflowDiscoveryRequest,
    WorkflowDiscoveryResponse
)

from app.services.secret_service import create_secret, update_secret, delete_secret
from app.services.secret_decrypt_service import decrypt_secret_for_test
from app.services.cicd_service import (
    promote_to_hubspot,
    check_workflow_status,
    get_workflow_actions,
    CICDServiceError,
    SecretDecryptionError,
    ActionNotManagedError,
    NoUpdateNeededError
)
from app.services.workflow_discovery_service import (
    discover_workflows,
    WorkflowDiscoveryError,
    SecretVerificationError
)
from app.workers.base import run_execution
from app.models.errors import (
    SecretPersistenceError,
    SecretPortalMismatchError,
    SecretForbiddenError,
    SecretNotFoundError,
    CicdSecretValidationError,
    CicdTokenInvalidError,
    CicdTokenMissingScopesError,
)
from app.models.source_code_conversion import (
    SourceCodeConversionRequest,
    SourceCodeConversionResponse,
    SourceCodeConversionErrorResponse
)
from app.services.source_code_conversion_service import (
    SourceCodeConversionService,
    MainNotFoundError,
    InvalidSourceError,
    SourceCodeConversionError
)
from os import getenv
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Detect if running in Google Cloud Run environment
IS_CLOUD_RUN = bool(getenv("K_SERVICE"))

# Configure structured logging with execution context
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s "
        "execution_id=%(execution_id)s "
        "status=%(status)s "
        "%(message)s"
    )
)
# Add custom filters for execution tracking and Sentry context
handler.addFilter(ExecutionContextFilter())
handler.addFilter(SentryContextFilter())

logging.basicConfig(level=logging.INFO, handlers=[handler])

# ----------------------------
# Sentry Error Tracking Configuration
# ----------------------------
if settings.sentry_dsn:
    # Configure logging integration for Sentry
    sentry_logging = LoggingIntegration(
        level=logging.INFO,      # Capture INFO and above as breadcrumbs
        event_level=logging.ERROR  # Send ERROR level events to Sentry
    )

    def before_send(event: Dict[str, Any] | None, hint: Dict[str, Any]) -> Dict[str, Any] | None:
        """
        Add custom metadata to Sentry events before sending.

        This function enriches Sentry events with application context
        including execution mode, environment, and service information
        to help with debugging and monitoring.
        """
        if event is None:
            return None

        # Add custom tags for filtering and grouping in Sentry
        event["tags"] = {
            **event.get("tags", {}),
            "execution_mode": settings.execution_mode,
            "is_cloud_run": IS_CLOUD_RUN,
            "service": settings.app_name,
        }

        # Add extra context for detailed debugging information
        event["extra"] = {
            **event.get("extra", {}),
            "environment_info": {
                "environment": settings.environment,
                "execution_mode": settings.execution_mode,
                "is_cloud_run": IS_CLOUD_RUN,
                "app_name": settings.app_name,
            }
        }

        return event

    # Initialize Sentry SDK with comprehensive configuration
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            FastApiIntegration(),  # FastAPI-specific error tracking
            sentry_logging         # Logging integration
        ],
        traces_sample_rate=settings.sentry_traces_sample_rate,  # Performance monitoring
        environment=settings.sentry_environment,
        release=settings.sentry_release,
        server_name=settings.sentry_server_name,
        debug=settings.sentry_debug,
        before_send=before_send,
        attach_stacktrace=True,    # Include stack traces for better debugging
        max_breadcrumbs=50,       # Maximum breadcrumb count for context
    )

    # Set global user context for Sentry (can be overridden per request)
    sentry_sdk.set_user({
        "id": "system",
        "environment": settings.environment,
        "execution_mode": settings.execution_mode,
    })

    # Set global tags for consistent filtering in Sentry
    sentry_sdk.set_tag("service", settings.app_name)
    sentry_sdk.set_tag("execution_mode", settings.execution_mode)
    sentry_sdk.set_tag("is_cloud_run", IS_CLOUD_RUN)

    logger.info("Sentry error tracking initialized", extra={
        "environment": settings.sentry_environment,
        "release": settings.sentry_release,
        "traces_sample_rate": settings.sentry_traces_sample_rate,
    })
else:
    logger.warning("SENTRY_DSN not configured - error tracking disabled")

# Initialize FastAPI application
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

# ----------------------------
# CORS (Cross-Origin Resource Sharing) Configuration
# ----------------------------
# Parse CORS origins from environment variable
# Supports both comma-separated string and list formats
# Example: CORS_ORIGINS="http://localhost:3000,https://app.example.com"
origins = (
    settings.cors_origins
    if isinstance(settings.cors_origins, list)
    else [o.strip() for o in settings.cors_origins.split(",")]
)

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ----------------------------
# API Routes
# ----------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for all unhandled exceptions.

    This middleware captures unhandled exceptions, adds context to Sentry,
    and returns a standardized error response. It filters sensitive headers
    and includes execution context when available.
    """
    # Add request context to Sentry for better debugging
    if settings.sentry_dsn:
        with sentry_sdk.configure_scope() as scope:
            # Filter sensitive headers to avoid exposing secrets
            safe_headers = {}
            for key, value in request.headers.items():
                if key.lower() not in ['authorization', 'cookie', 'x-api-key', 'x-auth-token']:
                    safe_headers[key] = value

            # Set request context in Sentry
            scope.set_context("request", {
                "url": str(request.url),
                "method": request.method,
                "headers": safe_headers,
                "client": {
                    "host": request.client.host if request.client else None,
                    "port": request.client.port if request.client else None,
                },
                "query_params": dict(request.query_params),
            })

            # Add execution context if available from request state
            if hasattr(request.state, 'execution_id'):
                scope.set_tag("execution_id", request.state.execution_id)
            if hasattr(request.state, 'status'):
                scope.set_tag("status", request.state.status)

        # Capture exception with additional context in Sentry
        sentry_sdk.capture_exception(exc)

    # Sanitize exception message to prevent secret leakage
    error_message = str(exc)

    # Filter out potential secret values from error messages
    sensitive_patterns = [
        'password', 'token', 'secret', 'key', 'credential',
        'authorization', 'bearer', 'api_key'
    ]

    for pattern in sensitive_patterns:
        if pattern.lower() in error_message.lower():
            error_message = f"Internal server error (sensitive information filtered)"
            break

    # Return standardized error response
    return JSONResponse(
        status_code=500,
        content={"error": error_message},
    )


@app.get("/health", response_model=HealthResponse)
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


@app.post("/execute")
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


@app.post(
    "/secrets",
    response_model=CreateSecretResponse,
    dependencies=[Depends(require_runtime_token)],
)
async def create_secret_endpoint(req: CreateSecretRequest):
    """
    Create a new encrypted secret.

    This endpoint creates a new secret with AES-GCM encryption and stores it
    securely in the database. The secret is encrypted with a unique data
    encryption key (DEK) that is wrapped using the key encryption key (KEK).

    For CICD-scoped secrets, this endpoint validates that the token has the
    required HubSpot API permissions before storing the secret in the database.
    The validation makes a test API call to HubSpot's automation/v4/flows endpoint
    and returns appropriate error messages for different failure scenarios:

    - 401: Token is invalid or expired
    - 403: Token lacks required HubSpot API scopes
    - 200: Token is valid with proper scopes

    Args:
        req: Secret creation request containing scope, portal ID, name, and value

    Returns:
        CreateSecretResponse: Confirmation of secret creation with generated ID

    Raises:
        HTTPException: For various validation and persistence errors with appropriate status codes
    """
    try:
        secret_id = await create_secret(
            scope=req.scope,
            portal_id=req.portal_id,
            action_id=req.action_id,
            name=req.name,
            value=req.value,
            created_by=req.created_by,
        )
        return CreateSecretResponse(ok=True, secret_id=secret_id)

    except CicdTokenInvalidError as e:
        # Token is invalid/expired (401)
        raise HTTPException(status_code=401, detail=str(e))

    except CicdTokenMissingScopesError as e:
        # Token lacks required scopes (403)
        raise HTTPException(status_code=403, detail=str(e))

    except CicdSecretValidationError as e:
        # General CICD validation error (400)
        raise HTTPException(status_code=400, detail=str(e))

    except SecretAlreadyExistsError as e:
        # Secret already exists (409)
        raise HTTPException(status_code=409, detail=str(e))

    except (SecretPersistenceError, RuntimeError) as e:
        # Database or other persistence errors (500)
        raise HTTPException(status_code=500, detail=str(e))


@app.put(
    "/secrets/{secret_id}",
    response_model=UpdateSecretResponse,
    dependencies=[Depends(require_runtime_token)],
)
def update_secret_endpoint(secret_id: UUID, req: UpdateSecretRequest):
    """
    Update an existing secret's value.

    This endpoint updates the value of an existing secret while maintaining
    the same metadata (scope, name, etc.). The new value is encrypted with
    a fresh data encryption key for security.

    Args:
        secret_id: UUID of the secret to update
        req: Update request containing the new secret value

    Returns:
        UpdateSecretResponse: Confirmation of successful update
    """
    update_secret(secret_id=secret_id, value=req.value)
    return UpdateSecretResponse(ok=True, secret_id=secret_id)


@app.post(
    "/cicd/promote",
    response_model=CicdPromoteResponse,
    dependencies=[Depends(require_runtime_token)],
)
async def cicd_promote(req: CicdPromoteRequest, force: bool = False, dry_run: bool = False):
    """
    [DEPRECATED] Promote source code to a HubSpot workflow action.

    This endpoint is deprecated. Use POST /cicd/workflow/{workflow_id}/action/{action_id}/promote instead.

    This endpoint allows CI/CD systems to update HubSpot workflow actions
    by providing source code and a CICD secret ID (containing the HubSpot token).

    Args:
        req: Promotion request with source code, secret ID, workflow ID, and action ID
        force: Force update even if action has no hash marker (default: False)
        dry_run: Perform dry run without making changes (default: False)
    """
    try:
        result = await promote_to_hubspot(
            source_code=req.source_code,
            cicd_secret_id=req.cicd_secret_id,
            workflow_id=req.workflow_id,
            action_id=req.action_id,
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


@app.post(
    "/cicd/workflow/{workflow_id}/action/{action_id}/promote",
    response_model=CicdPromoteResponse,
    dependencies=[Depends(require_runtime_token)],
)
async def promote_workflow_action(
    workflow_id: str,
    action_id: str,
    req: CicdPromoteByUrlRequest,
    force: bool = False,
    dry_run: bool = False,
):
    """
    Promote source code to a HubSpot workflow action using URL parameters.

    This is the new preferred endpoint that uses workflow_id and action_id
    from the URL path instead of request body. The old /cicd/promote endpoint
    is deprecated and will be removed in a future version.

    Args:
        workflow_id: HubSpot workflow ID from URL path
        action_id: HubSpot action ID from URL path  
        req: Request containing source code and CICD secret ID
        force: Force update even if action has no hash marker (default: False)
        dry_run: Perform dry run without making changes (default: False)
    """
    try:
        result = await promote_to_hubspot(
            source_code=req.source_code,
            cicd_secret_id=req.cicd_secret_id,
            workflow_id=workflow_id,
            action_id=action_id,
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
        return CicdPromoteResponse(
            ok=True,
            workflow_id=workflow_id,
            new_hash=str(e).split(" ")[-1],
            revision_id=None,
            action_index=None,
        )

    except (SecretDecryptionError, ActionNotManagedError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    except CICDServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logger.exception("Unexpected error in workflow action promote")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get(
    "/cicd/workflow/{workflow_id}/status",
    response_model=WorkflowStatusResponse,
    dependencies=[Depends(require_runtime_token)],
)
async def check_workflow_status_endpoint(
    workflow_id: str,
    cicd_secret_id: UUID,
    action_id: str,
    source_code: Optional[str] = None,
):
    """
    Check the status of a workflow action and its synchronization state.

    This endpoint helps with CICD onboarding by showing whether an action
    is managed by Novocode, if it's in sync with source code, and provides
    recommendations for next steps.

    Args:
        workflow_id: HubSpot workflow ID to check
        cicd_secret_id: ID of the CICD-scoped secret containing the HubSpot token
        action_id: HubSpot action ID to identify the target action within the workflow
        source_code: Optional source code to compare against the current action
    """
    # Validate input parameters
    if not workflow_id or not workflow_id.strip():
        raise HTTPException(
            status_code=400, detail="workflow_id cannot be empty")

    if not action_id or not action_id.strip():
        raise HTTPException(
            status_code=400, detail="action_id cannot be empty")

    try:
        result = await check_workflow_status(
            cicd_secret_id=cicd_secret_id,
            workflow_id=workflow_id.strip(),
            action_id=action_id.strip(),
            source_code=source_code,
        )

        return result

    except Exception as e:
        logger.exception("Unexpected error in workflow status check")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get(
    "/cicd/workflow/{workflow_id}",
    response_model=GetWorkflowActionsResponse,
    dependencies=[Depends(require_runtime_token)],
)
async def get_workflow_actions_endpoint(
    workflow_id: str,
    cicd_secret_id: UUID,
):
    """
    Get all custom code actions from a HubSpot workflow.

    This endpoint retrieves all CUSTOM_CODE type actions from a workflow,
    including their source code, runtime settings, and associated secret names.

    Args:
        workflow_id: HubSpot workflow ID to fetch actions from
        cicd_secret_id: CICD secret ID for authentication
    """
    # Validate input parameters
    if not workflow_id or not workflow_id.strip():
        raise HTTPException(
            status_code=400, detail="workflow_id cannot be empty")

    try:
        result = await get_workflow_actions(
            cicd_secret_id=cicd_secret_id,
            workflow_id=workflow_id.strip(),
        )

        return result

    except CICDServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logger.exception("Unexpected error in get workflow actions")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post(
    "/workflows/discover",
    response_model=WorkflowDiscoveryResponse,
    dependencies=[Depends(require_runtime_token)],
)
async def discover_workflows_endpoint(req: WorkflowDiscoveryRequest):
    """
    Discover HubSpot workflows with custom code actions in a portal.

    This endpoint scans all workflows in a portal to find custom code actions
    that can be managed by the CICD system. It handles pagination automatically
    and can optionally process and store actions in the database.

    Args:
        req: Discovery request containing all required parameters
    """
    try:
        result = await discover_workflows(
            secret_id=req.secret_id,
            portal_id=req.portal_id,
            owner_id=req.owner_id,
            portal_id_int=req.portal_id_int,
            process_actions=req.process_actions,
        )

        return result

    except SecretVerificationError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except WorkflowDiscoveryError as e:
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logger.exception("Unexpected error in workflow discovery")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/convert-source-code", response_model=SourceCodeConversionResponse)
async def convert_source_code(req: SourceCodeConversionRequest):
    """
    Convert Python source code to include telemetry tracking.
    
    This endpoint wraps user Python code with telemetry helper functions
    and decorates the main(event) entrypoint with @telemetry_track().
    
    Args:
        req: Conversion request containing source code and optional telemetry parameters
        
    Returns:
        SourceCodeConversionResponse: Converted source code with telemetry
        
    Raises:
        HTTPException: For various conversion errors with appropriate status codes
    """
    try:
        service = SourceCodeConversionService()
        converted_code, warnings = service.convert_source_code(
            source_code=req.source_code,
            action_id=req.action_id,
            workflow_id=req.workflow_id,
            secret=req.secret
        )
        
        return SourceCodeConversionResponse(
            converted_source_code=converted_code,
            warnings=warnings
        )
        
    except MainNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    except InvalidSourceError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    except SourceCodeConversionError as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    except Exception as e:
        logger.exception("Unexpected error in source code conversion")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.delete(
    "/secrets/{secret_id}",
    response_model=DeleteSecretResponse,
    dependencies=[Depends(require_runtime_token)]
)
def delete_secret_endpoint(secret_id: UUID, req: DeleteSecretRequest):
    """
    Delete an existing secret.

    This endpoint deletes a secret after performing authorization checks
    to ensure the user has permission to delete secrets from the specified portal.

    Args:
        secret_id: UUID of the secret to delete
        req: Delete request containing portal ID and user ID for authorization

    Returns:
        DeleteSecretResponse: Confirmation of successful deletion

    Raises:
        HTTPException: If authorization fails or secret is not found
    """
    try:
        delete_secret(
            secret_id=secret_id,
            portal_id=req.portal_id,
            user_id=req.user_id
        )
        return DeleteSecretResponse(ok=True, secret_id=secret_id)

    except (SecretNotFoundError, SecretPortalMismatchError, SecretForbiddenError) as e:
        # Use default status code if exception doesn't have status_code attribute
        status_code = getattr(e, 'status_code', 404)
        raise HTTPException(status_code=status_code, detail=str(e))

    except SecretPersistenceError as e:
        # SecretPersistenceError should have status_code from base class
        status_code = getattr(e, 'status_code', 500)
        raise HTTPException(status_code=status_code, detail=str(e))
