from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional, Dict, Any
from datetime import datetime


class Action(BaseModel):
    """Represents a custom code action stored in the database"""
    
    id: UUID = Field(
        ...,
        description="Unique identifier for the action",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    
    owner_id: UUID = Field(
        ...,
        description="ID of the user who owns this action",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    
    name: str = Field(
        ...,
        description="Name of the action",
        examples=["Customer Onboarding Action"],
    )
    
    description: Optional[str] = Field(
        None,
        description="Description of what the action does",
        examples=["Processes new customer onboarding data"],
    )
    
    language: str = Field(
        ...,
        description="Programming language of the action",
        examples=["python", "javascript"],
        pattern="^(python|javascript)$",
    )
    
    filepath: str = Field(
        ...,
        description="Path to the source code file in storage",
        examples=["portal_uuid/action_uuid/action.py"],
    )
    
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration for the action",
        examples=[{"timeout": 30, "memory": "256MB"}],
    )
    
    is_active: bool = Field(
        default=True,
        description="Whether the action is currently active",
        examples=[True],
    )
    
    created_at: datetime = Field(
        ...,
        description="Timestamp when the action was created",
    )
    
    updated_at: datetime = Field(
        ...,
        description="Timestamp when the action was last updated",
    )
    
    template_id: Optional[UUID] = Field(
        None,
        description="ID of the template this action is based on",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    
    portal_id: UUID = Field(
        ...,
        description="Portal ID this action belongs to",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    
    workflow_id: Optional[str] = Field(
        None,
        description="HubSpot workflow ID this action belongs to",
        examples=["123456789"],
    )
    
    action_id: Optional[str] = Field(
        None,
        description="HubSpot action ID within the workflow",
        examples=["1", "2"],
    )
    
    source: str = Field(
        ...,
        description="Source system where this action was discovered",
        examples=["hubspot"],
    )
    
    cicd_search_token: Optional[str] = Field(
        None,
        description="CICD search token for identifying this action",
        examples=["CI_CD_ABCDEFGH"],
    )


class CreateActionRequest(BaseModel):
    """Request to create a new action"""
    
    owner_id: UUID = Field(..., description="ID of the action owner")
    name: str = Field(..., description="Action name")
    description: Optional[str] = Field(None, description="Action description")
    language: str = Field(..., description="Action language (python/javascript)")
    portal_id: UUID = Field(..., description="Portal ID")
    workflow_id: Optional[str] = Field(None, description="Workflow ID")
    source: str = Field(..., description="Source system")
    config: Dict[str, Any] = Field(default_factory=dict, description="Action config")


class CreateActionResponse(BaseModel):
    """Response when creating an action"""
    
    ok: bool = Field(..., description="Whether creation was successful")
    action_id: UUID = Field(..., description="ID of the created action")
    cicd_search_token: str = Field(..., description="Generated CICD search token")
    filepath: str = Field(..., description="Storage path for the action")
