from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional, List, Dict, Any


class WorkflowDiscoveryRequest(BaseModel):
    """
    Request to discover HubSpot workflows with custom code actions.
    
    This endpoint scans all workflows in a portal to find custom code actions
    that can be managed by the CICD system.
    """
    
    secret_id: UUID = Field(
        ...,
        description="ID of the CICD-scoped secret containing the HubSpot token",
        examples=["82caec1c-5c66-4c40-9e6a-7ea7c4bac922"],
    )
    
    portal_id: UUID = Field(
        ...,
        description="Portal ID to discover workflows for",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    
    owner_id: UUID = Field(
        ...,
        description="UUID of the action owner",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    
    portal_id_int: int = Field(
        ...,
        description="Portal ID as integer for event data",
        examples=[12345678],
    )
    
    process_actions: bool = Field(
        default=True,
        description="Whether to process and store actions (default: True)",
        examples=[True],
    )


class CustomCodeAction(BaseModel):
    """Represents a custom code action found in a workflow"""
    
    name: str = Field(
        ...,
        description="Name of the workflow containing this action",
        examples=["Customer Onboarding"],
    )
    
    id: str = Field(
        ...,
        description="ID of the workflow containing this action",
        examples=["123456789"],
    )
    
    language: Optional[str] = Field(
        None,
        description="Programming language of the action",
        examples=["PYTHON", "JAVASCRIPT", "NODE20X", "PYTHON39"],
    )
    
    action_id: str = Field(
        ...,
        description="ID of the custom code action",
        examples=["action_123456"],
    )
    
    # New fields for action processing results
    database_action_id: Optional[UUID] = Field(
        None,
        description="Database UUID of the created action",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    
    filepath: Optional[str] = Field(
        None,
        description="Storage path for the source code file",
        examples=["portal_uuid/action_uuid/action.py"],
    )
    
    event_filepath: Optional[str] = Field(
        None,
        description="Storage path for the event.json file",
        examples=["portal_uuid/action_uuid/event.json"],
    )
    
    input_fields: Optional[Dict[str, Any]] = Field(
        None,
        description="Extracted input fields from the source code",
        examples=[{"a": 10, "b": 0}],
    )
    
    processed: bool = Field(
        default=False,
        description="Whether this action has been processed and stored",
        examples=[True],
    )
    
    error: Optional[str] = Field(
        None,
        description="Error message if processing failed",
        examples=["Action already exists for workflow"],
    )


class WorkflowDiscoveryResponse(BaseModel):
    """
    Response from workflow discovery containing simplified action information.
    """
    
    ok: bool = Field(
        ...,
        description="Indicates whether the discovery was successful",
        examples=[True],
    )
    
    portal_id: UUID = Field(
        ...,
        description="Portal ID that was scanned",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    
    total_workflows: int = Field(
        ...,
        description="Total number of workflows scanned",
        examples=[42],
    )
    
    total_code_actions: int = Field(
        ...,
        description="Total number of custom code actions found",
        examples=[5],
    )
    
    actions: List[CustomCodeAction] = Field(
        ...,
        description="List of custom code actions with simplified information",
    )
