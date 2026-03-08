from pydantic import BaseModel, Field
from typing import Optional, List


class SourceCodeConversionRequest(BaseModel):
    """
    Request to convert Python or JavaScript source code to include telemetry tracking.
    
    This endpoint wraps user code with telemetry helper functions
    and decorates the main(event) entrypoint with appropriate telemetry tracking.
    Supports both Python (@telemetry_track decorator) and JavaScript (@telemetryTrack decorator).
    """
    source_code: str = Field(
        ...,
        min_length=1,
        description="Raw Python or JavaScript source code to be converted",
        examples=[
            "def main(event):\n    print('Hello World')", 
            "export async function main(event) {\n    console.log('Hello World');\n}",
            "exports.main = async function(event) {\n    console.log('Hello World');\n}"
        ],
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
    
    skip_lint: bool = Field(
        False,
        description="Skip linting validation (default: False)",
        examples=[False],
    )


class SourceCodeConversionResponse(BaseModel):
    """
    Response containing the converted source code with telemetry.
    """
    converted_source_code: str = Field(
        ...,
        description="Python or JavaScript source code with telemetry wrapper and decorator applied",
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
        examples=["MAIN_NOT_FOUND", "INVALID_SOURCE", "CONVERSION_FAILED", "LINT_FAILED"],
    )
    
    message: str = Field(
        ...,
        description="Human-readable error message",
    )
    
    details: Optional[dict] = Field(
        None,
        description="Additional error details",
    )


class PythonLintRequest(BaseModel):
    """
    Request to lint Python source code.
    """
    source_code: str = Field(
        ...,
        min_length=1,
        description="Python source code to lint",
        examples=["def main(event):\n    return {'message': 'Hello World'}"],
    )


class PythonLintResponse(BaseModel):
    """
    Response containing Python linting results.
    """
    passed: bool = Field(
        ...,
        description="Whether the code passed linting",
    )
    
    errors: List[str] = Field(
        default_factory=list,
        description="List of linting error messages",
    )
    
    warnings: List[str] = Field(
        default_factory=list,
        description="List of linting warnings (if any)",
    )


class PythonLintErrorResponse(BaseModel):
    """
    Error response for Python linting failures.
    """
    error_code: str = Field(
        ...,
        description="Machine-readable error code",
        examples=["LINT_ERROR", "INVALID_SOURCE"],
    )
    
    message: str = Field(
        ...,
        description="Human-readable error message",
    )


class JavaScriptLintRequest(BaseModel):
    """
    Request to lint JavaScript source code.
    """
    source_code: str = Field(
        ...,
        min_length=1,
        description="JavaScript source code to lint",
        examples=[
            "export async function main(event) {\n    return { message: 'Hello World' };\n}",
            "exports.main = async function(event) {\n    return { message: 'Hello World' };\n}"
        ],
    )


class JavaScriptLintResponse(BaseModel):
    """
    Response containing JavaScript linting results.
    """
    passed: bool = Field(
        ...,
        description="Whether the code passed linting",
    )
    
    errors: List[str] = Field(
        default_factory=list,
        description="List of linting error messages",
    )
    
    warnings: List[str] = Field(
        default_factory=list,
        description="List of linting warnings (if any)",
    )


class JavaScriptLintErrorResponse(BaseModel):
    """
    Error response for JavaScript linting failures.
    """
    error_code: str = Field(
        ...,
        description="Machine-readable error code",
        examples=["LINT_ERROR", "INVALID_SOURCE"],
    )
    
    message: str = Field(
        ...,
        description="Human-readable error message",
    )
