import logging
from uuid import UUID
from typing import Optional

from app.services.secret_decrypt_service import decrypt_secret_for_test
from app.services.hubspot_service import (
    get_workflow,
    find_action_by_action_id,
    get_action_source_code,
    generate_source_hash,
    inject_hash_marker,
    extract_hash_marker,
    build_updated_workflow_payload,
    put_workflow,
    WorkflowNotFoundError,
    ActionNotFoundError,
    HubSpotAPIError,
    HubSpotServiceError,
)
from app.models.cicd import (
    CicdPromoteRequest,
    CicdPromoteResponse,
    WorkflowStatusResponse,
    GetWorkflowActionsRequest,
    GetWorkflowActionsResponse,
    WorkflowActionResponse,
    WorkflowStatus,
)
logger = logging.getLogger(__name__)


class CICDServiceError(Exception):
    """Base exception for CICD service errors"""
    pass


class SecretDecryptionError(CICDServiceError):
    """Raised when CICD secret cannot be decrypted"""
    pass


class ActionNotManagedError(CICDServiceError):
    """Raised when target action is not managed by hsemulator (no hash marker)"""
    pass


class NoUpdateNeededError(CICDServiceError):
    """Raised when action is already up to date"""
    pass


async def decrypt_cicd_secret(secret_id: UUID) -> str:
    """Decrypt a CICD-scoped secret and return the HubSpot token"""
    try:
        secret_data = decrypt_secret_for_test(secret_id)
        
        if secret_data["scope"] != "cicd":
            raise SecretDecryptionError(
                f"Secret {secret_id} has scope '{secret_data['scope']}', expected 'cicd'"
            )
        
        return secret_data["value"]
        
    except Exception as e:
        if isinstance(e, SecretDecryptionError):
            raise
        logger.error(f"Failed to decrypt CICD secret {secret_id}: {e}")
        raise SecretDecryptionError(f"Failed to decrypt CICD secret: {e}")


async def promote_to_hubspot(
    source_code: str,
    cicd_secret_id: UUID,
    workflow_id: str,
    action_id: str,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Promote source code to a HubSpot workflow action.
    
    Args:
        source_code: Source code to deploy
        cicd_secret_id: ID of the CICD secret containing HubSpot token
        workflow_id: HubSpot workflow ID
        action_id: HubSpot action ID to identify target action
        force: Force update even if action has no hash marker
        dry_run: Perform dry run without making changes
    
    Returns:
        Dictionary with promotion results
    """
    # Decrypt the CICD secret to get HubSpot token
    token = await decrypt_cicd_secret(cicd_secret_id)
    
    # Fetch the current workflow
    try:
        workflow = await get_workflow(token, workflow_id)
    except WorkflowNotFoundError as e:
        raise CICDServiceError(f"Workflow not found: {e}")
    except HubSpotAPIError as e:
        raise CICDServiceError(f"Failed to fetch workflow: {e}")
    
    # Find the target action
    try:
        action_index = find_action_by_action_id(workflow, action_id)
    except ActionNotFoundError as e:
        raise CICDServiceError(f"Target action not found: {e}")
    except HubSpotServiceError as e:
        raise CICDServiceError(f"Error finding action: {e}")
    
    # Get current action source code
    try:
        existing_source = get_action_source_code(workflow, action_index)
    except HubSpotServiceError as e:
        raise CICDServiceError(f"Error getting action source: {e}")
    
    # Generate hash for new source code
    new_hash = generate_source_hash(source_code)
    promoted_source = inject_hash_marker(source_code, new_hash)
    
    # Check if update is needed
    existing_hash = extract_hash_marker(existing_source)
    if existing_hash == new_hash:
        raise NoUpdateNeededError(f"Action already up to date (hash {new_hash})")
    
    # Check if action is managed by hsemulator (has hash marker)
    if not existing_hash and not force:
        raise ActionNotManagedError(
            "Target action does not appear to be managed by hsemulator "
            "(missing hsemulator-sha marker). Use force=True to override."
        )
    
    if not existing_hash and force:
        logger.warning(f"Overwriting action with no hash marker due to force=True")
    
    logger.info(f"Updating action in workflow {workflow_id} at index {action_index}")
    if existing_hash:
        logger.debug(f"Existing hash: {existing_hash[:8]}..., new hash: {new_hash[:8]}...")
    else:
        logger.debug(f"Adding new action with hash: {new_hash[:8]}...")
    
    # Build updated workflow payload
    try:
        updated_payload = build_updated_workflow_payload(
            workflow, action_index, promoted_source
        )
    except HubSpotServiceError as e:
        raise CICDServiceError(f"Error building workflow payload: {e}")
    
    # Handle dry run
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "workflow_id": workflow_id,
            "new_hash": new_hash,
            "action_index": action_index,
            "existing_hash": existing_hash,
        }
    
    # Update the workflow
    try:
        result = await put_workflow(token, workflow_id, updated_payload)
    except HubSpotAPIError as e:
        raise CICDServiceError(f"Failed to update workflow: {e}")
    
    return {
        "ok": True,
        "workflow_id": workflow_id,
        "new_hash": new_hash,
        "revision_id": result.get("revisionId"),
        "action_index": action_index,
        "existing_hash": existing_hash,
    }


async def check_workflow_status(
    cicd_secret_id: UUID,
    workflow_id: str,
    action_id: str,
    source_code: Optional[str] = None,
) -> WorkflowStatusResponse:
    """
    Check the status of a workflow action and its synchronization state.
    
    Args:
        cicd_secret_id: ID of the CICD secret containing HubSpot token
        workflow_id: HubSpot workflow ID to check
        action_id: HubSpot action ID to identify the target action
        source_code: Optional source code to compare against current action
    
    Returns:
        WorkflowStatusResponse with detailed status information
    """
    # Generate hash for provided source code (if any) - do this once
    source_hash = generate_source_hash(source_code) if source_code else None
    
    # Try to decrypt the CICD secret
    try:
        token = await decrypt_cicd_secret(cicd_secret_id)
    except SecretDecryptionError as e:
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            action_id=action_id,
            status="access_denied",
            action_found=False,
            has_hash_marker=False,
            current_hash=None,
            source_hash=source_hash,
            action_index=None,
            recommendation="Access denied: Invalid credentials or permissions",
            can_promote=False,
        )
    
    # Try to fetch the workflow
    try:
        workflow = await get_workflow(token, workflow_id)
    except WorkflowNotFoundError:
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            action_id=action_id,
            status="workflow_not_found",
            action_found=False,
            has_hash_marker=False,
            current_hash=None,
            source_hash=source_hash,
            action_index=None,
            recommendation="Workflow not found. Check the workflow ID and permissions.",
            can_promote=False,
        )
    except HubSpotAPIError as e:
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            action_id=action_id,
            status="access_denied",
            action_found=False,
            has_hash_marker=False,
            current_hash=None,
            source_hash=source_hash,
            action_index=None,
            recommendation="API access denied. Check token permissions and workflow access.",
            can_promote=False,
        )
    
    # Try to find the target action
    try:
        action_index = find_action_by_action_id(workflow, action_id)
        action_found = True
    except ActionNotFoundError:
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            action_id=action_id,
            status="not_found",
            action_found=False,
            has_hash_marker=False,
            current_hash=None,
            source_hash=source_hash,
            action_index=None,
            recommendation=f"Action with actionId '{action_id}' not found in workflow. Check the action_id.",
            can_promote=False,
        )
    except HubSpotServiceError as e:
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            action_id=action_id,
            status="access_denied",
            action_found=False,
            has_hash_marker=False,
            current_hash=None,
            source_hash=source_hash,
            action_index=None,
            recommendation="Service error occurred while accessing workflow.",
            can_promote=False,
        )
    
    # Get current action source code
    try:
        current_source = get_action_source_code(workflow, action_index)
    except HubSpotServiceError as e:
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            action_id=action_id,
            status="access_denied",
            action_found=action_found,
            has_hash_marker=False,
            current_hash=None,
            source_hash=source_hash,
            action_index=action_index,
            recommendation="Service error occurred while accessing action source.",
            can_promote=False,
        )
    
    # Extract current hash and check if action is managed
    current_hash = extract_hash_marker(current_source)
    has_hash_marker = current_hash is not None
    
    # Determine status and recommendation
    if not has_hash_marker:
        status = "unmanaged"
        recommendation = "Action exists but is not managed by hsemulator (no hash marker). Use POST /cicd/promote with force=True to take ownership."
        can_promote = True
    elif source_code and current_hash != source_hash:
        status = "out_of_sync"
        recommendation = "Action is out of sync with provided source code. Use POST /cicd/promote to update."
        can_promote = True
    elif source_code and current_hash == source_hash:
        status = "in_sync"
        recommendation = "Action is in sync with provided source code. No update needed."
        can_promote = True
    else:
        # Has hash marker but no source code provided for comparison
        status = "managed_unknown_sync"
        recommendation = "Action is managed by hsemulator and has a hash marker. Provide source_code to check if it's in sync."
        can_promote = True
    
    return WorkflowStatusResponse(
        workflow_id=workflow_id,
        action_id=action_id,
        status=status,
        action_found=action_found,
        has_hash_marker=has_hash_marker,
        current_hash=current_hash,
        source_hash=source_hash,
        action_index=action_index,
        recommendation=recommendation,
        can_promote=can_promote,
    )


async def get_workflow_actions(
    cicd_secret_id: UUID,
    workflow_id: str,
) -> GetWorkflowActionsResponse:
    """
    Get all custom code actions from a HubSpot workflow.
    
    Args:
        cicd_secret_id: ID of the CICD secret containing HubSpot token
        workflow_id: HubSpot workflow ID to fetch actions from
    
    Returns:
        GetWorkflowActionsResponse with all custom code actions found
    """
    # Decrypt the CICD secret to get HubSpot token
    try:
        token = await decrypt_cicd_secret(cicd_secret_id)
    except SecretDecryptionError as e:
        raise CICDServiceError(f"Failed to decrypt CICD secret: {e}")
    
    # Fetch the workflow
    try:
        workflow = await get_workflow(token, workflow_id)
    except WorkflowNotFoundError as e:
        raise CICDServiceError(f"Workflow not found: {e}")
    except HubSpotAPIError as e:
        raise CICDServiceError(f"Failed to fetch workflow: {e}")
    
    # Extract all custom code actions
    actions = workflow.get("actions", [])
    if not isinstance(actions, list):
        raise CICDServiceError("Workflow missing 'actions' array")
    
    custom_actions = []
    for action in actions:
        if action.get("type") == "CUSTOM_CODE":
            action_response = WorkflowActionResponse(
                action_id=action.get("actionId", ""),
                type=action.get("type", ""),
                source_code=action.get("sourceCode"),
                runtime=action.get("runtime"),
                secret_names=action.get("secretNames", []),
            )
            custom_actions.append(action_response)
    
    return GetWorkflowActionsResponse(
        workflow_id=workflow_id,
        actions=custom_actions,
        total_count=len(custom_actions),
    )
