"""
Workflow discovery endpoints.

This blueprint handles workflow discovery and management operations.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from app.auth import require_runtime_token
from app.models.workflows import (
    WorkflowDiscoveryRequest,
    WorkflowDiscoveryResponse
)
from app.services.workflow_discovery_service import (
    discover_workflows,
    WorkflowDiscoveryError,
    SecretVerificationError
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workflows",
    tags=["Workflow Discovery"],
    responses={
        400: {"description": "Bad Request - Invalid parameters"},
        401: {"description": "Unauthorized - Invalid or missing authentication token"},
        404: {"description": "Not Found - Portal or secret not found"},
        500: {"description": "Internal Server Error - Discovery processing failed"}
    }
)


@router.post(
    "/discover",
    response_model=WorkflowDiscoveryResponse,
    dependencies=[Depends(require_runtime_token)],
    summary="Discover Workflows",
    description="""
    Discover HubSpot workflows with custom code actions for CI/CD onboarding.
    
    This endpoint scans all workflows in a portal to find custom code actions
    that can be managed by the CICD system. It handles pagination automatically
    and can optionally process and store actions in the database.
    
    **Discovery Process:**
    - Scans all workflows in the specified portal
    - Identifies CUSTOM_CODE type actions
    - Extracts action metadata and source code
    - Validates action compatibility
    - Optionally stores discovered actions
    
    **Portal Analysis Features:**
    - **Workflow Inventory**: Complete list of workflows
    - **Action Detection**: Identifies all custom code actions
    - **Metadata Extraction**: Action details and configuration
    - **Compatibility Check**: Validates CICD management feasibility
    - **Bulk Processing**: Efficient handling of large portals
    
    **Discovery Options:**
    - **process_actions**: Store discovered actions in database
    - **include_inactive**: Include inactive workflows
    - **detailed_analysis**: Perform deep code analysis
    
    **Use Cases:**
    - Initial portal assessment for CICD adoption
    - Bulk onboarding of existing workflows
    - Portal audit and documentation
    - Migration planning and preparation
    - Security assessment of custom actions
    
    **Parameters:**
    - **secret_id**: Secret for HubSpot API authentication
    - **portal_id**: HubSpot portal identifier
    - **owner_id**: Portal owner for authorization
    - **portal_id_int**: Numeric portal ID
    - **process_actions**: Store results in database
    
    **Flow:**
    1. Validate secret and portal access
    2. Authenticate with HubSpot API
    3. Paginate through all workflows
    4. Extract custom code actions from each workflow
    5. Analyze action compatibility
    6. Optionally store in database
    7. Return comprehensive discovery results
    
    **Response Format:**
    Returns detailed information about discovered workflows and actions,
    including metadata, source code, and processing status.
    
    **Performance Considerations:**
    - Large portals may require several minutes to process
    - Pagination is handled automatically
    - Results are streamed for memory efficiency
    - Progress tracking available via execution logs
    """,
    responses={
        200: {
            "description": "Workflow discovery completed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "portal_id": "123456",
                        "total_workflows": 25,
                        "workflows_with_custom_code": 8,
                        "total_actions": 12,
                        "processed_actions": 12,
                        "workflows": [
                            {
                                "id": "workflow_123",
                                "name": "Lead Processing",
                                "status": "ACTIVE",
                                "actions": [
                                    {
                                        "id": "action_456",
                                        "name": "Custom Validation",
                                        "type": "CUSTOM_CODE",
                                        "compatible": True,
                                        "source_code": "function main(event) { ... }"
                                    }
                                ]
                            }
                        ],
                        "processing_summary": {
                            "discovered": 12,
                            "processed": 12,
                            "skipped": 0,
                            "errors": 0
                        }
                    }
                }
            }
        },
        400: {"description": "Invalid request parameters or portal configuration"},
        401: {"description": "Unauthorized - Invalid authentication token"},
        404: {"description": "Portal not found or secret invalid"},
        500: {"description": "HubSpot API error or discovery processing failed"}
    }
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
