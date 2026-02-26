import logging
import secrets
from uuid import UUID
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.db import get_supabase
from app.models.actions import Action, CreateActionRequest
from app.models.errors import SecretPersistenceError

logger = logging.getLogger(__name__)

def create_action(
    *,
    owner_id: UUID,
    name: str,
    description: Optional[str],
    language: str,
    portal_id: UUID,
    workflow_id: Optional[str],
    action_id: Optional[str] = None,
    source: str,
    config: Dict[str, Any],
    filepath: str,
    template_id: Optional[UUID] = None,
) -> Action:
    """Create a new action record in the database"""
    supabase = get_supabase()

    # Validate language
    if language not in ['python', 'javascript']:
        raise ValueError(
            f"Invalid language: {language}. Must be 'python' or 'javascript'")

    payload = {
        "owner_id": str(owner_id),
        "name": name,
        "description": description,
        "language": language,
        "filepath": filepath,
        "config": config,
        "is_active": True,
        "portal_id": str(portal_id),
        "source": source,
    }

    if workflow_id:
        payload["workflow_id"] = workflow_id

    if action_id:
        payload["action_id"] = action_id

    if template_id:
        payload["template_id"] = str(template_id)

    try:
        result = supabase.table("actions").insert(payload).execute()

        if not result.data or not isinstance(result.data, list):
            raise SecretPersistenceError(
                "Action insert succeeded but no data was returned")

        action_data = result.data[0]

        return Action(
            id=UUID(action_data["id"]),
            owner_id=UUID(action_data["owner_id"]),
            name=action_data["name"],
            description=action_data.get("description"),
            language=action_data["language"],
            filepath=action_data["filepath"],
            config=action_data.get("config", {}),
            is_active=action_data["is_active"],
            created_at=datetime.fromisoformat(action_data["created_at"]),
            updated_at=datetime.fromisoformat(action_data["updated_at"]),
            template_id=UUID(action_data["template_id"]) if action_data.get(
                "template_id") else None,
            portal_id=UUID(action_data["portal_id"]),
            workflow_id=action_data.get("workflow_id"),
            action_id=action_data.get("action_id"),
            source=action_data["source"],
        )

    except ValueError:
        raise
    except Exception:
        logger.exception(
            "Failed to create action",
            extra={
                "owner_id": str(owner_id),
                "action_name": name,
                "portal_id": str(portal_id),
                "language": language,
            },
        )
        raise SecretPersistenceError("Failed to create action")


def get_action_by_id(action_id: UUID) -> Optional[Action]:
    """Get an action by its ID"""
    supabase = get_supabase()

    try:
        result = (
            supabase
            .table("actions")
            .select("*")
            .eq("id", str(action_id))
            .execute()
        )

        if not result.data:
            return None

        action_data = result.data[0]

        return Action(
            id=UUID(action_data["id"]),
            owner_id=UUID(action_data["owner_id"]),
            name=action_data["name"],
            description=action_data.get("description"),
            language=action_data["language"],
            filepath=action_data["filepath"],
            config=action_data.get("config", {}),
            is_active=action_data["is_active"],
            created_at=datetime.fromisoformat(action_data["created_at"]),
            updated_at=datetime.fromisoformat(action_data["updated_at"]),
            template_id=UUID(action_data["template_id"]) if action_data.get(
                "template_id") else None,
            portal_id=UUID(action_data["portal_id"]),
            workflow_id=action_data.get("workflow_id"),
            source=action_data["source"],
        )

    except Exception:
        logger.exception(
            "Failed to fetch action",
            extra={"action_id": str(action_id)},
        )
        raise SecretPersistenceError("Failed to fetch action")


def get_actions_by_portal(portal_id: UUID) -> List[Action]:
    """Get all actions for a specific portal"""
    supabase = get_supabase()

    try:
        result = (
            supabase
            .table("actions")
            .select("*")
            .eq("portal_id", str(portal_id))
            .execute()
        )

        actions = []
        for action_data in result.data or []:
            actions.append(Action(
                id=UUID(action_data["id"]),
                owner_id=UUID(action_data["owner_id"]),
                name=action_data["name"],
                description=action_data.get("description"),
                language=action_data["language"],
                filepath=action_data["filepath"],
                config=action_data.get("config", {}),
                is_active=action_data["is_active"],
                created_at=datetime.fromisoformat(action_data["created_at"]),
                updated_at=datetime.fromisoformat(action_data["updated_at"]),
                template_id=UUID(action_data["template_id"]) if action_data.get(
                    "template_id") else None,
                portal_id=UUID(action_data["portal_id"]),
                workflow_id=action_data.get("workflow_id"),
                source=action_data["source"],
            ))

        return actions

    except Exception:
        logger.exception(
            "Failed to fetch actions by portal",
            extra={"portal_id": str(portal_id)},
        )
        raise SecretPersistenceError("Failed to fetch actions by portal")


def update_action_file_path(action_id: UUID, filepath: str) -> None:
    """Update the file path of an action"""
    supabase = get_supabase()

    try:
        result = (
            supabase
            .table("actions")
            .update({"filepath": filepath, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", str(action_id))
            .execute()
        )

        if not result.data:
            raise SecretPersistenceError("Action not found for update")

    except Exception:
        logger.exception(
            "Failed to update action file path",
            extra={"action_id": str(action_id), "filepath": filepath}
        )
        raise SecretPersistenceError("Failed to update action file path")


def delete_action(action_id: UUID) -> None:
    """Delete an action from the database"""
    supabase = get_supabase()

    try:
        result = (
            supabase
            .table("actions")
            .delete()
            .eq("id", str(action_id))
            .execute()
        )

        if not result.data:
            logger.warning(f"Action {action_id} not found for deletion")

    except Exception:
        logger.exception(
            "Failed to delete action",
            extra={"action_id": str(action_id)}
        )
        raise SecretPersistenceError("Failed to delete action")
