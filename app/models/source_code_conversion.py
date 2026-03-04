from pydantic import BaseModel, Field
from typing import Optional, List


class SourceCodeConversionRequest(BaseModel):
    """
    Request to convert Python source code to include telemetry tracking.
    
    This endpoint wraps user Python code with telemetry helper functions
    and decorates the main(event) entrypoint with @telemetry_track().
    """
    source_code: str = Field(
        ...,
        min_length=1,
        description="Raw Python source code to be converted",
        examples=["def main(event):\n    print('Hello World')"],
    )
    
    action_id: Optional[str] = Field(
        None,
        description="Action ID for telemetry tracking (uses template default if not provided)",
        examples=["action-123456"],
    )
    
    workflow_id: Optional[int] = Field(
        None,
        description="Workflow ID for telemetry tracking (uses template default if not provided)",
        examples=[123456],
    )
    
    secret: Optional[str] = Field(
        None,
        description="Secret for telemetry tracking (uses template default if not provided)",
        examples=["your-secret-key"],
    )


class SourceCodeConversionResponse(BaseModel):
    """
    Response containing the converted source code with telemetry.
    """
    converted_source_code: str = Field(
        ...,
        description="Python source code with telemetry wrapper and decorator applied",
    )
    
    warnings: List[str] = Field(
        default_factory=list,
        description="List of warnings about the conversion process",
    )


class SourceCodeConversionErrorResponse(BaseModel):
    """
    Error response for source code conversion failures.
    """
    error_code: str = Field(
        ...,
        description="Machine-readable error code",
        examples=["MAIN_NOT_FOUND", "INVALID_SOURCE", "CONVERSION_FAILED"],
    )
    
    message: str = Field(
        ...,
        description="Human-readable error message",
    )
    
    details: Optional[dict] = Field(
        None,
        description="Additional error details",
    )
