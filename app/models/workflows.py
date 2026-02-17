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
        ...,
        description="Programming language of the action",
        examples=["PYTHON", "JAVASCRIPT"],
    )
    
    action_id: str = Field(
        ...,
        description="ID of the custom code action",
        examples=["action_123456"],
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
