import logging
import secrets
from uuid import UUID
from typing import Optional
from datetime import datetime

from app.db import get_supabase
from app.utils.crypto import generate_telemetry_secret
from app.services.hubspot_service import generate_source_hash

logger = logging.getLogger(__name__)


def create_action_registry_entry(
    *,
    id: UUID,
    workflow_id: str,
    portal_id: int,
    account_uuid: UUID,
    portal_uuid: UUID,
    source_hash: str,
    action_name: str,
    action_id: str,
    workflow_name: Optional[str] = None,
    portal_name: Optional[str] = None,
    environment: str = "production",
    max_mismatches: int = 3,
) -> dict:
    """
    Create a new entry in the action_registry table.
    
    Args:
        id: UUID for the action registry entry
        workflow_id: HubSpot workflow ID
        portal_id: HubSpot portal ID (integer)
        account_uuid: Account UUID
        portal_uuid: Portal UUID
        source_hash: Hash of the source code
        action_name: Name of the action
        action_id: HubSpot action ID
        workflow_name: Optional workflow name
        portal_name: Optional portal name
        environment: Environment (default: 'production')
        max_mismatches: Maximum allowed mismatches (default: 3)
        
    Returns:
        dict: The created action registry record
        
    Raises:
        Exception: If database operation fails
    """
    supabase = get_supabase()
    
    # Generate a random secret key for this action
    secret_key = generate_telemetry_secret()
    
    payload = {
        "id": str(id),
        "workflow_id": workflow_id,
        "portal_id": portal_id,
        "account_uuid": str(account_uuid),
        "portal_uuid": str(portal_uuid),
        "source_hash": source_hash,
        "secret_key": secret_key,
        "is_active": True,
        "environment": environment,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "usage_count": 0,
        "max_mismatches": max_mismatches,
        "mismatch_count": 0,
        "failure_count": 0,
        "action_name": action_name,
        "action_id": action_id,
        "workflow_name": workflow_name,
        "portal_name": portal_name,
    }
    
    try:
        result = supabase.table("action_registry").insert(payload).execute()
        
        if not result.data or not isinstance(result.data, list):
            raise Exception("Action registry insert succeeded but no data was returned")
        
        logger.info(
            "Created action registry entry",
            extra={
                "action_registry_id": str(id),
                "workflow_id": workflow_id,
                "action_id": action_id,
                "portal_id": portal_id,
            },
        )
        
        return result.data[0]
        
    except Exception as e:
        logger.exception(
            "Failed to create action registry entry",
            extra={
                "action_registry_id": str(id),
                "workflow_id": workflow_id,
                "action_id": action_id,
                "portal_id": portal_id,
            },
        )
        raise Exception(f"Failed to create action registry entry: {e}")


def get_action_registry_entry(action_registry_id: UUID) -> Optional[dict]:
    """
    Get an action registry entry by ID.
    
    Args:
        action_registry_id: UUID of the action registry entry
        
    Returns:
        Optional[dict]: The action registry entry or None if not found
    """
    supabase = get_supabase()
    
    try:
        result = (
            supabase
            .table("action_registry")
            .select("*")
            .eq("id", str(action_registry_id))
            .execute()
        )
        
        if not result.data:
            return None
            
        return result.data[0]
        
    except Exception as e:
        logger.exception(
            "Failed to fetch action registry entry",
            extra={"action_registry_id": str(action_registry_id)},
        )
        raise Exception(f"Failed to fetch action registry entry: {e}")


def update_action_registry_usage(action_registry_id: UUID) -> None:
    """
    Update usage statistics for an action registry entry.
    
    Args:
        action_registry_id: UUID of the action registry entry to update
    """
    supabase = get_supabase()
    
    try:
        result = (
            supabase
            .table("action_registry")
            .update({
                "usage_count": supabase.raw("usage_count + 1"),
                "last_used_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            })
            .eq("id", str(action_registry_id))
            .execute()
        )
        
        if not result.data:
            logger.warning(f"Action registry entry {action_registry_id} not found for usage update")
        
    except Exception as e:
        logger.exception(
            "Failed to update action registry usage",
            extra={"action_registry_id": str(action_registry_id)},
        )
        raise Exception(f"Failed to update action registry usage: {e}")


def update_action_registry_secret_key(action_registry_id: UUID, new_secret_key: str, new_source_hash: str) -> dict:
    """
    Update the secret key and source hash for an existing action registry entry.
    
    Args:
        action_registry_id: UUID of the action registry entry to update
        new_secret_key: New secret key for telemetry tracking
        new_source_hash: New hash of the source code
        
    Returns:
        dict: The updated action registry record
        
    Raises:
        Exception: If database operation fails
    """
    supabase = get_supabase()
    
    payload = {
        "secret_key": new_secret_key,
        "source_hash": new_source_hash,
        "updated_at": datetime.utcnow().isoformat(),
        "last_used_at": datetime.utcnow().isoformat(),
    }
    
    try:
        result = (
            supabase
            .table("action_registry")
            .update(payload)
            .eq("id", str(action_registry_id))
            .execute()
        )
        
        if not result.data:
            raise Exception(f"Action registry entry {action_registry_id} not found for update")
        
        logger.info(
            "Updated action registry secret key",
            extra={
                "action_registry_id": str(action_registry_id),
                "new_source_hash": new_source_hash,
            },
        )
        
        return result.data[0]
        
    except Exception as e:
        logger.exception(
            "Failed to update action registry secret key",
            extra={"action_registry_id": str(action_registry_id)},
        )
        raise Exception(f"Failed to update action registry secret key: {e}")


def get_action_registry_by_workflow_and_action(workflow_id: str, action_id: str) -> Optional[dict]:
    """
    Get an action registry entry by workflow_id and action_id.
    
    Args:
        workflow_id: HubSpot workflow ID
        action_id: HubSpot action ID
        
    Returns:
        Optional[dict]: The action registry entry or None if not found
    """
    supabase = get_supabase()
    
    try:
        result = (
            supabase
            .table("action_registry")
            .select("*")
            .eq("workflow_id", workflow_id)
            .eq("action_id", action_id)
            .execute()
        )
        
        if not result.data:
            return None
            
        return result.data[0]
        
    except Exception as e:
        logger.exception(
            "Failed to fetch action registry entry by workflow and action",
            extra={"workflow_id": workflow_id, "action_id": action_id},
        )
        raise Exception(f"Failed to fetch action registry entry: {e}")
