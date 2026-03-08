"""
CI/CD endpoints for workflow management and promotion.

This blueprint handles CI/CD operations including workflow promotion,
status checking, and action retrieval.
"""

from uuid import UUID
from typing import Optional
import logging

from fastapi import APIRouter, HTTPException, Depends, Query

from app.auth import require_runtime_token
from app.models.cicd import (
    CicdPromoteRequest,
    CicdPromoteByUrlRequest,
    CicdPromoteResponse,
    WorkflowStatusResponse,
    GetWorkflowActionsRequest,
    GetWorkflowActionsResponse,
)
from app.services.cicd_service import (
    promote_to_hubspot,
    check_workflow_status,
    get_workflow_actions,
    CICDServiceError,
    SecretDecryptionError,
    ActionNotManagedError,
    NoUpdateNeededError
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cicd",
    tags=["CI/CD Operations"],
    responses={
        400: {"description": "Bad Request - Invalid parameters or secret decryption failed"},
        401: {"description": "Unauthorized - Invalid or missing authentication token"},
        403: {"description": "Forbidden - Insufficient permissions"},
        404: {"description": "Not Found - Workflow or action not found"},
        500: {"description": "Internal Server Error - HubSpot API or processing error"}
    }
)


@router.post(
    "/promote",
    response_model=CicdPromoteResponse,
    dependencies=[Depends(require_runtime_token)],
    summary="Promote Source Code (Deprecated)",
    description="""
    ⚠️ **DEPRECATED** - Use `/cicd/workflow/{workflow_id}/action/{action_id}/promote` instead.
    
    Promote source code to a HubSpot workflow action for CI/CD integration.
    
    This endpoint allows CI/CD systems to update HubSpot workflow actions
    by providing source code and a CICD secret ID containing the HubSpot token.
    
    **Deprecation Notice:**
    This endpoint is deprecated and will be removed in a future version.
    The new preferred endpoint uses URL parameters for better RESTful design.
    
    **Promotion Process:**
    1. Decrypt CICD secret to get HubSpot token
    2. Validate token permissions and access
    3. Convert source code with telemetry (if enabled)
    4. Update workflow action in HubSpot
    5. Track revision with hash markers
    
    **Parameters:**
    - **force**: Skip hash validation and force update
    - **dry_run**: Validate without making changes
    - **telemetry**: Add telemetry tracking to code
    
    **Flow:**
    1. Validate request and authentication
    2. Decrypt CICD secret for HubSpot access
    3. Optionally apply telemetry conversion
    4. Update action in HubSpot workflow
    5. Return promotion results with hash
    """,
    responses={
        200: {
            "description": "Promotion completed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "workflow_id": "123456789",
                        "new_hash": "abc123def456",
                        "revision_id": "rev_123456",
                        "action_index": 2
                    }
                }
            }
        },
        400: {"description": "Invalid parameters or secret decryption failed"},
        401: {"description": "Unauthorized - Invalid authentication token"},
        500: {"description": "HubSpot API error or processing failure"}
    }
)
async def cicd_promote(req: CicdPromoteRequest, force: bool = False, dry_run: bool = False, telemetry: bool = False):
    """
    [DEPRECATED] Promote source code to a HubSpot workflow action.

    This endpoint is deprecated. Use POST /cicd/workflow/{workflow_id}/action/{action_id}/promote instead.

    This endpoint allows CI/CD systems to update HubSpot workflow actions
    by providing source code and a CICD secret ID (containing the HubSpot token).

    Args:
        req: Promotion request with source code, secret ID, workflow ID, and action ID
        force: Force update even if action has no hash marker (default: False)
        dry_run: Perform dry run without making changes (default: False)
        telemetry: Whether to apply telemetry conversion (default: False)
    """
    try:
        result = await promote_to_hubspot(
            source_code=req.source_code,
            cicd_secret_id=req.cicd_secret_id,
            workflow_id=req.workflow_id,
            action_id=req.action_id,
            force=force,
            dry_run=dry_run,
            telemetry=telemetry,  # Use the telemetry parameter
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


@router.post(
    "/workflow/{workflow_id}/action/{action_id}/promote",
    response_model=CicdPromoteResponse,
    dependencies=[Depends(require_runtime_token)],
    summary="Promote Workflow Action",
    description="""
    Promote source code to a HubSpot workflow action using RESTful URL parameters.
    
    This is the **preferred endpoint** for CI/CD integration. It uses workflow_id
    and action_id from the URL path instead of the request body for better
    RESTful design and caching.
    
    **Promotion Features:**
    - **Telemetry Integration**: Optional telemetry wrapper injection
    - **Hash Tracking**: Automatic hash markers for change detection
    - **Dry Run Mode**: Validate without making changes
    - **Force Update**: Override hash validation when needed
    - **Revision Tracking**: Complete audit trail of changes
    
    **Source Code Processing:**
    - Python: @telemetry_track decorator injection
    - JavaScript: @telemetryTrack decorator or function wrapping
    - Linting: Automatic code quality validation
    - Validation: Syntax and structure checks
    
    **Security & Validation:**
    - CICD secret decryption for HubSpot access
    - Token permission validation
    - Workflow and action existence verification
    - Source code security scanning
    
    **Parameters:**
    - **workflow_id**: HubSpot workflow identifier (URL path)
    - **action_id**: Target action within workflow (URL path)
    - **force**: Force update even if no hash marker (default: false)
    - **dry_run**: Validate without applying changes (default: false)
    - **telemetry**: Add telemetry tracking (request body)
    
    **Flow:**
    1. Extract workflow_id and action_id from URL
    2. Validate authentication and permissions
    3. Decrypt CICD secret for HubSpot API access
    4. Process source code (telemetry, linting, validation)
    5. Update workflow action in HubSpot
    6. Generate and store hash markers
    7. Return promotion results
    
    **Use Cases:**
    - Automated CI/CD pipeline integration
    - Git-based workflow deployment
    - Automated testing and promotion
    - Multi-environment deployment strategies
    """,
    responses={
        200: {
            "description": "Action promoted successfully",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "workflow_id": "123456789",
                        "new_hash": "abc123def456",
                        "revision_id": "rev_123456",
                        "action_index": 2
                    }
                }
            }
        },
        400: {"description": "Invalid parameters, secret decryption failed, or action not managed"},
        401: {"description": "Unauthorized - Invalid authentication token"},
        404: {"description": "Workflow or action not found"},
        500: {"description": "HubSpot API error or processing failure"}
    }
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
        req: Request containing source code, CICD secret ID, and telemetry option
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
            telemetry=req.telemetry,
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


@router.get(
    "/workflow/{workflow_id}/status",
    response_model=WorkflowStatusResponse,
    dependencies=[Depends(require_runtime_token)],
    summary="Check Workflow Status",
    description="""
    Check the synchronization status of a workflow action for CI/CD onboarding.
    
    This endpoint helps with CI/CD onboarding by showing whether an action
    is managed by Novocode, if it's in sync with source code, and provides
    recommendations for next steps.
    
    **Status Information Provided:**
    - **Management Status**: Whether the action is managed by Novocode
    - **Sync Status**: If the action code matches the provided source code
    - **Hash Markers**: Current and expected hash values
    - **Recommendations**: Actionable next steps for onboarding
    - **Metadata**: Action details and configuration
    
    **Onboarding Workflow:**
    1. Check if action is already managed
    2. Compare current code with provided source code
    3. Analyze hash markers and sync status
    4. Provide specific onboarding recommendations
    5. Return detailed status report
    
    **Use Cases:**
    - Initial CI/CD onboarding of existing workflows
    - Verification of deployment status
    - Troubleshooting sync issues
    - Pre-deployment validation
    
    **Parameters:**
    - **workflow_id**: HubSpot workflow identifier
    - **cicd_secret_id**: CICD secret for HubSpot API access
    - **action_id**: Target action within the workflow
    - **source_code**: Optional source code for comparison
    
    **Flow:**
    1. Validate workflow and action identifiers
    2. Authenticate with HubSpot using CICD secret
    3. Retrieve current action configuration
    4. Analyze management and sync status
    5. Compare with provided source code (if any)
    6. Generate recommendations and status report
    """,
    responses={
        200: {
            "description": "Workflow status retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "is_managed": True,
                        "is_in_sync": True,
                        "current_hash": "abc123def456",
                        "expected_hash": "abc123def456",
                        "recommendations": ["Action is properly managed and in sync"],
                        "action_details": {
                            "id": "action_123",
                            "name": "Custom Code Action",
                            "type": "CUSTOM_CODE"
                        }
                    }
                }
            }
        },
        400: {"description": "Invalid workflow_id or action_id parameters"},
        401: {"description": "Unauthorized - Invalid authentication token"},
        404: {"description": "Workflow or action not found"},
        500: {"description": "HubSpot API error or processing failure"}
    }
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


@router.get(
    "/workflow/{workflow_id}",
    response_model=GetWorkflowActionsResponse,
    dependencies=[Depends(require_runtime_token)],
    summary="Get Workflow Actions",
    description="""
    Retrieve all custom code actions from a HubSpot workflow.
    
    This endpoint fetches all CUSTOM_CODE type actions from a workflow,
    including their source code, runtime settings, and associated secret names.
    Ideal for workflow analysis, backup, and migration purposes.
    
    **Action Information Retrieved:**
    - **Source Code**: Complete action source code
    - **Runtime Settings**: Execution environment configuration
    - **Secret Names**: Associated secret identifiers
    - **Action Metadata**: ID, name, type, and position
    - **Dependencies**: Required libraries and modules
    
    **Use Cases:**
    - Workflow backup and documentation
    - Code review and analysis
    - Migration between environments
    - Security audit of custom actions
    - Bulk operations on multiple actions
    
    **Security Considerations:**
    - Requires valid CICD secret for authentication
    - Only returns CUSTOM_CODE type actions
    - Secret names are exposed, not secret values
    - Access is logged for audit purposes
    
    **Parameters:**
    - **workflow_id**: HubSpot workflow identifier
    - **cicd_secret_id**: CICD secret for HubSpot API access
    
    **Flow:**
    1. Validate workflow identifier
    2. Authenticate with HubSpot using CICD secret
    3. Retrieve workflow definition
    4. Filter for CUSTOM_CODE actions only
    5. Extract source code and metadata
    6. Return structured action list
    
    **Response Format:**
    Returns an array of actions with complete details including
    source code, runtime settings, and associated secret names.
    """,
    responses={
        200: {
            "description": "Workflow actions retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "actions": [
                            {
                                "id": "action_123",
                                "name": "Process Lead",
                                "type": "CUSTOM_CODE",
                                "source_code": "function main(event) { ... }",
                                "runtime_settings": {
                                    "runtime": "node18.x",
                                    "memory": 512,
                                    "timeout": 30
                                },
                                "secret_names": ["hubspot_api_key"],
                                "position": 1
                            }
                        ],
                        "total_count": 1
                    }
                }
            }
        },
        400: {"description": "Invalid workflow_id parameter"},
        401: {"description": "Unauthorized - Invalid authentication token"},
        404: {"description": "Workflow not found"},
        500: {"description": "HubSpot API error or processing failure"}
    }
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
