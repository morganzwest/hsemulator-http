import logging
import asyncio
import os
import re
from uuid import UUID
from typing import Dict, Any, Optional
from datetime import datetime

from app.db.actions_repo import create_action
from app.services.storage_service import create_action_files, StorageServiceError
from app.models.actions import Action

logger = logging.getLogger(__name__)


class ActionProcessingError(Exception):
    """Base exception for action processing errors"""
    pass


class ActionAlreadyExistsError(ActionProcessingError):
    """Raised when an action already exists for the given workflow"""
    pass


def normalize_language(language: str) -> str:
    """Normalize language string to match database values"""
    if not language or not language.strip():
        raise ValueError("Language cannot be None or empty")
    
    language = language.lower().strip()
    
    # Map various HubSpot language formats to our database format
    if language in ['python', 'python39', 'python3', 'py']:
        return 'python'
    elif language in ['javascript', 'js', 'node', 'node20x', 'node18x', 'nodejs']:
        return 'javascript'
    else:
        raise ValueError(f"Unsupported language: {language}")


async def process_custom_action(
    *,
    workflow_name: str,
    workflow_id: str,
    action_id: str,
    language: str,
    source_code: str,
    portal_id: UUID,
    owner_id: UUID,
    portal_id_int: int,
    description: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process a custom code action found during workflow discovery.
    
    This function:
    1. Creates a database record for the action
    2. Stores the source code in Supabase storage
    3. Generates and stores an event.json file
    4. Returns comprehensive action details
    
    Args:
        workflow_name: Name of the workflow containing the action
        workflow_id: HubSpot workflow ID
        action_id: HubSpot action ID
        language: Programming language (PYTHON, JAVASCRIPT, etc.)
        source_code: The source code content
        portal_id: Portal UUID
        owner_id: UUID of the action owner
        portal_id_int: Portal ID as integer for event data
        description: Optional description of the action
        config: Optional configuration dictionary
        
    Returns:
        Dictionary containing all action details including:
        - action_id: Database UUID of the created action
        - cicd_search_token: Generated CICD search token
        - filepath: Storage path for the source code
        - event_filepath: Storage path for the event file
        - input_fields: Extracted input fields
        - language: Normalized language string
        - workflow_id: HubSpot workflow ID
        - action_name: Action name (derived from workflow)
        
    Raises:
        ActionProcessingError: If processing fails
        ActionAlreadyExistsError: If action already exists
        StorageServiceError: If file operations fail
    """
    try:
        # Normalize language
        normalized_language = normalize_language(language)
        
        # Check if action already exists for this workflow and action
        existing_action = get_action_by_workflow_and_action_id(workflow_id, action_id)
        if existing_action:
            logger.warning(
                f"Action already exists for workflow {workflow_id}, action {action_id}",
                extra={
                    "workflow_id": workflow_id,
                    "action_id": action_id,
                    "existing_action_id": str(existing_action.id),
                }
            )
            raise ActionAlreadyExistsError(f"Action already exists for workflow {workflow_id}, action {action_id}")
        
        # Create action in database first to get the UUID
        action = create_action(
            owner_id=owner_id,
            name=f"{workflow_name} - Custom Code Action",
            description=description or f"Custom code action from workflow: {workflow_name}",
            language=normalized_language,
            portal_id=portal_id,
            workflow_id=workflow_id,
            action_id=action_id,
            source="hubspot",
            config=config or {},
            filepath="",  # Will be updated after file upload
        )
        
        logger.info(
            f"Created action record: {action.id}",
            extra={
                "action_id": str(action.id),
                "workflow_id": workflow_id,
                "language": normalized_language,
            }
        )
        
        try:
            # Create files in storage
            source_filepath, event_filepath, input_fields = await create_action_files(
                portal_id=portal_id,
                action_id=action.id,
                source_code=source_code,
                language=normalized_language,
                portal_id_int=portal_id_int,
            )
            
            # Update the action record with the file path
            from app.db.actions_repo import update_action_file_path
            update_action_file_path(action.id, source_filepath)
            
        except Exception as e:
            # Cleanup: delete the action record since file upload failed
            logger.error(
                f"File upload failed for action {action.id}, cleaning up database record",
                extra={"action_id": str(action.id), "error": str(e)}
            )
            try:
                from app.db.actions_repo import delete_action
                delete_action(action.id)
            except Exception as cleanup_error:
                logger.error(
                    f"Failed to cleanup action record {action.id}",
                    extra={"action_id": str(action.id), "cleanup_error": str(cleanup_error)}
                )
            raise StorageServiceError(f"File upload failed, cleaned up action record: {e}")
        
        logger.info(
            f"Successfully processed action: {action.id}",
            extra={
                "action_id": str(action.id),
                "source_filepath": source_filepath,
                "event_filepath": event_filepath,
                "input_fields_count": len(input_fields),
                "cicd_search_token": action.cicd_search_token,
            }
        )
        
        # Return comprehensive action details
        return {
            "action_id": str(action.id),
            "cicd_search_token": action.cicd_search_token,
            "filepath": source_filepath,
            "event_filepath": event_filepath,
            "input_fields": input_fields,
            "language": normalized_language,
            "workflow_id": workflow_id,
            "action_name": action.name,
            "description": action.description,
            "created_at": action.created_at.isoformat(),
            "portal_id": str(portal_id),
        }
        
    except ActionAlreadyExistsError:
        raise
    except StorageServiceError:
        raise
    except ValueError:
        raise ActionProcessingError(f"Invalid language: {language}")
    except Exception as e:
        logger.exception(
            "Failed to process custom action",
            extra={
                "workflow_id": workflow_id,
                "action_id": action_id,
                "language": language,
                "portal_id": str(portal_id),
            }
        )
        raise ActionProcessingError(f"Failed to process custom action: {e}")


def sanitize_path_component(component: str) -> str:
    """Sanitize path components to prevent injection and traversal attacks"""
    if not component:
        raise ValueError("Path component cannot be empty")
    
    # Convert to string and remove dangerous characters
    component = re.sub(r'[^\w\-]', '', str(component))
    
    # Validate length and format
    if not component or len(component) > 100:
        raise ValueError("Invalid path component format or length")
    
    return component


def get_action_by_workflow_and_action_id(workflow_id: str, action_id: str) -> Optional[Action]:
    """Get an action by its HubSpot workflow ID and action ID"""
    if not workflow_id or not workflow_id.strip():
        raise ValueError("workflow_id cannot be None or empty")
    
    from app.db import get_supabase
    
    try:
        supabase = get_supabase()
        
        # Query by workflow_id AND action_id
        result = (
            supabase
            .table("actions")
            .select("id,workflow_id,action_id,cicd_search_token")
            .eq("workflow_id", workflow_id)
            .eq("action_id", action_id)
            .execute()
        )
        
        if not result.data:
            return None
        
        action_data = result.data[0]
        
        # Return minimal action object for existence check
        return Action(
            id=UUID(action_data["id"]),
            owner_id=UUID("00000000-0000-0000-0000-000000000000"),  # Placeholder
            name="",  # Placeholder
            language=action_data.get("language", "python"),
            filepath="",  # Placeholder
            workflow_id=action_data.get("workflow_id"),
            action_id=action_data.get("action_id"),
            cicd_search_token=action_data.get("cicd_search_token"),
            # Set required fields with defaults
            description=None,
            config={},
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            template_id=None,
            portal_id=UUID("00000000-0000-0000-0000-000000000000"),  # Placeholder
            source="hubspot",
        )
        
    except Exception:
        logger.exception(
            "Failed to fetch action by workflow and action ID",
            extra={"workflow_id": workflow_id, "action_id": action_id}
        )
        return None


async def process_action_batch(
    actions_data: list[Dict[str, Any]],
    portal_id: UUID,
    owner_id: UUID,
    portal_id_int: int
) -> list[Dict[str, Any]]:
    """
    Process multiple actions in batch concurrently.
    
    Args:
        actions_data: List of action data from workflow discovery
        portal_id: Portal UUID
        owner_id: UUID of the action owner
        portal_id_int: Portal ID as integer for event data
        
    Returns:
        List of processed action details
    """
    async def process_single_action(action_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            result = await process_custom_action(
                workflow_name=action_data.get("workflow_name", "Unknown Workflow"),
                workflow_id=action_data.get("workflow_id"),
                action_id=action_data.get("action_id"),
                language=action_data.get("language"),
                source_code=action_data.get("source_code"),
                portal_id=portal_id,
                owner_id=owner_id,
                portal_id_int=portal_id_int,
                description=action_data.get("description"),
                config=action_data.get("config"),
            )
            return result
            
        except ActionAlreadyExistsError:
            logger.info(
                f"Skipping existing action for workflow {action_data.get('workflow_id')}"
            )
            return None
        except Exception as e:
            logger.error(
                f"Failed to process action from workflow {action_data.get('workflow_id')}: {e}"
            )
            return None
    
    # Process all actions concurrently
    tasks = [process_single_action(action_data) for action_data in actions_data]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out None results and exceptions
    processed_actions = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Unexpected error in batch processing: {result}")
        elif result is not None:
            processed_actions.append(result)
    
    return processed_actions
