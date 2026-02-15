from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional, Literal


class CicdPromoteRequest(BaseModel):
    """
    Request to promote source code to a HubSpot workflow action.
    
    The CICD secret ID is used to retrieve and decrypt the HubSpot token
    from the encrypted secrets store, ensuring no raw tokens are passed.
    """
    source_code: str = Field(
        ...,
        min_length=1,
        description="Source code to deploy to the HubSpot action",
        examples=["def main():\n    print('Hello World')"],
    )
    
    cicd_secret_id: UUID = Field(
        ...,
        description="ID of the CICD-scoped secret containing the HubSpot token",
        examples=["82caec1c-5c66-4c40-9e6a-7ea7c4bac922"],
    )
    
    workflow_id: str = Field(
        ...,
        min_length=1,
        description="HubSpot workflow ID to update",
        examples=["123456789"],
    )
    
    search_key: str = Field(
        ...,
        min_length=1,
        description="Secret name to identify the target action within the workflow",
        examples=["MY_ACTION_SECRET"],
    )


class CicdPromoteResponse(BaseModel):
    """
    Response returned after successfully promoting source code to HubSpot.
    """
    ok: bool = Field(
        ...,
        description="Indicates whether the promotion was successful",
        examples=[True],
    )
    
    workflow_id: str = Field(
        ...,
        description="ID of the updated workflow",
        examples=["123456789"],
    )
    
    new_hash: str = Field(
        ...,
        description="SHA256 hash of the deployed source code",
        examples=["a1b2c3d4e5f6..."],
    )
    
    revision_id: Optional[str] = Field(
        None,
        description="New revision ID of the workflow after update",
        examples=["rev_123456789"],
    )
    
    action_index: Optional[int] = Field(
        None,
        description="Index of the updated action within the workflow",
        examples=[0],
    )


class WorkflowAction(BaseModel):
    """Internal model representing a HubSpot workflow action"""
    type: str
    source_code: Optional[str] = None
    secret_names: Optional[list[str]] = None
    runtime: Optional[str] = None


# Workflow Status Check Models

WorkflowStatus = Literal[
    "in_sync",
    "out_of_sync", 
    "unmanaged",
    "not_found",
    "workflow_not_found",
    "access_denied",
    "managed_unknown_sync"
]


class WorkflowStatusResponse(BaseModel):
    """
    Response containing workflow action status and synchronization information.
    """
    workflow_id: str = Field(
        ...,
        description="ID of the checked workflow",
        examples=["123456789"],
    )
    
    search_key: str = Field(
        ...,
        description="Secret name that was searched for",
        examples=["MY_ACTION_SECRET"],
    )
    
    status: WorkflowStatus = Field(
        ...,
        description="Current synchronization status of the action",
        examples=["out_of_sync"],
    )
    
    action_found: bool = Field(
        ...,
        description="Whether the target action was found in the workflow",
        examples=[True],
    )
    
    has_hash_marker: bool = Field(
        ...,
        description="Whether the action has an hsemulator hash marker",
        examples=[True],
    )
    
    current_hash: Optional[str] = Field(
        None,
        description="Hash extracted from the current action source code",
        examples=["abc123..."],
    )
    
    source_hash: Optional[str] = Field(
        None,
        description="Hash of the provided source code (if any)",
        examples=["def456..."],
    )
    
    action_index: Optional[int] = Field(
        None,
        description="Index of the action within the workflow",
        examples=[2],
    )
    
    recommendation: str = Field(
        ...,
        description="Recommended next steps based on the status",
        examples=["Action is out of sync. Use POST /cicd/promote to update."],
    )
    
    can_promote: bool = Field(
        ...,
        description="Whether the action can be promoted using the CICD endpoint",
        examples=[True],
    )
