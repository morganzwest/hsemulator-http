import logging
from uuid import UUID

from app.services.secret_decrypt_service import decrypt_secret_for_test
from app.services.hubspot_service import (
    get_workflow,
    find_action_by_secret,
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
    search_key: str,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Promote source code to a HubSpot workflow action.
    
    Args:
        source_code: Source code to deploy
        cicd_secret_id: ID of the CICD secret containing HubSpot token
        workflow_id: HubSpot workflow ID
        search_key: Secret name to identify target action
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
        action_index = find_action_by_secret(workflow, search_key)
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
    
    logger.info(f"Updating action: {existing_hash or 'none'} -> {new_hash}")
    
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
