"""
Code processing endpoints.

This blueprint handles source code conversion, linting, and telemetry injection.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.models.source_code_conversion import (
    SourceCodeConversionRequest,
    SourceCodeConversionResponse,
    SourceCodeConversionErrorResponse,
    PythonLintRequest,
    PythonLintResponse,
    PythonLintErrorResponse,
    JavaScriptLintRequest,
    JavaScriptLintResponse,
    JavaScriptLintErrorResponse
)
from app.services.source_code_conversion_service import (
    SourceCodeConversionService,
    MainNotFoundError,
    InvalidSourceError,
    SourceCodeConversionError,
    LintError
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Code Processing"],
    responses={
        400: {"description": "Bad Request - Invalid source code or parameters"},
        422: {"description": "Unprocessable Entity - Linting errors found"},
        500: {"description": "Internal Server Error - Processing failed"}
    }
)


@router.post(
    "/convert-source-code", 
    response_model=SourceCodeConversionResponse,
    summary="Convert Source Code",
    description="""
    Convert Python or JavaScript source code to include telemetry tracking.
    
    This endpoint wraps user code with telemetry helper functions
    and decorates the main(event) entrypoint with appropriate telemetry tracking.
    Supports both Python and JavaScript with language-specific optimizations.
    
    **Language Support:**
    - **Python**: @telemetry_track decorator injection
    - **JavaScript**: @telemetryTrack decorator or function wrapping
    - **TypeScript**: Support for TypeScript syntax and modules
    
    **Telemetry Features:**
    - **Performance Tracking**: Execution time measurement
    - **Error Monitoring**: Automatic error capture and reporting
    - **Usage Analytics**: Function call tracking and metrics
    - **Debug Information**: Enhanced logging and debugging support
    
    **Code Processing Steps:**
    1. Parse and validate source code syntax
    2. Identify main(event) entrypoint
    3. Inject telemetry decorators/wrappers
    4. Add helper functions for tracking
    5. Optional linting and validation
    6. Return converted code with warnings
    
    **Conversion Options:**
    - **skip_lint**: Bypass code quality checks
    - **telemetry_level**: Control tracking verbosity
    - **preserve_formatting**: Maintain original code style
    - **include_helpers**: Add utility functions
    
    **Use Cases:**
    - Preparing code for HubSpot workflow deployment
    - Adding monitoring to existing functions
    - Automated code enhancement in CI/CD pipelines
    - Standardizing telemetry across workflows
    
    **Parameters:**
    - **source_code**: Original function code to convert
    - **action_id**: Workflow action identifier
    - **workflow_id**: Parent workflow identifier
    - **secret**: Optional secret for telemetry configuration
    - **skip_lint**: Skip code quality validation
    
    **Flow:**
    1. Validate input parameters and source code
    2. Detect programming language and syntax
    3. Parse AST to identify entrypoint
    4. Inject telemetry decorators/wrappers
    5. Add helper functions and imports
    6. Perform optional linting validation
    7. Return converted code with any warnings
    
    **Security Considerations:**
    - Code is parsed safely without execution
    - No external dependencies are introduced
    - Original functionality is preserved
    - Telemetry data is sanitized and filtered
    """,
    responses={
        200: {
            "description": "Source code converted successfully",
            "content": {
                "application/json": {
                    "example": {
                        "converted_source_code": "@telemetry_track\nfunction main(event) {\n  // Original code with telemetry\n  return processEvent(event);\n}",
                        "warnings": [
                            "Added telemetry tracking decorator",
                            "Imported telemetry helper functions"
                        ]
                    }
                }
            }
        },
        400: {"description": "Invalid source code or missing main() function"},
        422: {"description": "Code linting errors found"},
        500: {"description": "Code conversion processing failed"}
    }
)
async def convert_source_code(req: SourceCodeConversionRequest):
    """
    Convert Python or JavaScript source code to include telemetry tracking.
    
    This endpoint wraps user code with telemetry helper functions
    and decorates the main(event) entrypoint with appropriate telemetry tracking.
    Supports both Python (@telemetry_track decorator) and JavaScript (@telemetryTrack decorator or function wrapping).
    
    Args:
        req: Conversion request containing source code and optional telemetry parameters
        
    Returns:
        SourceCodeConversionResponse: Converted source code with telemetry
        
    Raises:
        HTTPException: For various conversion errors with appropriate status codes
    """
    try:
        service = SourceCodeConversionService()
        converted_code, warnings = service.convert_source_code(
            source_code=req.source_code,
            action_id=req.action_id,
            workflow_id=req.workflow_id,
            secret=req.secret,
            skip_lint=req.skip_lint
        )
        
        return SourceCodeConversionResponse(
            converted_source_code=converted_code,
            warnings=warnings
        )
        
    except MainNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    except InvalidSourceError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    except LintError as e:
        raise HTTPException(status_code=422, detail=str(e))
        
    except SourceCodeConversionError as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    except Exception as e:
        logger.exception("Unexpected error in source code conversion")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/lint/python", 
    response_model=PythonLintResponse,
    summary="Lint Python Code",
    description="""
    Lint Python source code using ruff for code quality validation.
    
    This endpoint provides standalone Python code linting functionality
    without any code modification or telemetry injection. Uses ruff
    for fast, accurate Python code analysis.
    
    **Linting Features:**
    - **Syntax Validation**: Python syntax checking
    - **Style Guide**: PEP 8 and custom style rules
    - **Security Analysis**: Common security issue detection
    - **Performance**: Code efficiency recommendations
    - **Best Practices**: Python idioms and patterns
    
    **Ruff Configuration:**
    - Fast Rust-based linting engine
    - Configurable rule sets
    - Automatic fixing suggestions
    - Import sorting and organization
    - Unused import and variable detection
    
    **Error Categories:**
    - **Errors**: Critical syntax and runtime issues
    - **Warnings**: Style and potential problems
    - **Info**: Suggestions and improvements
    - **Security**: Security vulnerabilities and risks
    
    **Use Cases:**
    - Pre-commit code validation
    - CI/CD pipeline quality gates
    - Code review automation
    - Educational feedback for developers
    - Technical debt assessment
    
    **Parameters:**
    - **source_code**: Python code to analyze
    - **config**: Optional ruff configuration
    - **severity_level**: Minimum issue severity to report
    
    **Flow:**
    1. Parse Python source code
    2. Apply ruff linting rules
    3. Categorize issues by severity
    4. Generate fix suggestions
    5. Return structured linting report
    
    **Response Format:**
    Returns pass/fail status with categorized error and warning messages
    including line numbers, rule codes, and fix suggestions.
    """,
    responses={
        200: {
            "description": "Python code linted successfully",
            "content": {
                "application/json": {
                    "example": {
                        "passed": True,
                        "errors": [],
                        "warnings": [
                            {
                                "line": 15,
                                "column": 10,
                                "message": "Unused variable 'result'",
                                "rule": "F841",
                                "fix_suggestion": "Remove or use the variable"
                            }
                        ]
                    }
                }
            }
        },
        400: {"description": "Invalid Python source code"},
        422: {"description": "Code linting errors found"},
        500: {"description": "Linting processing failed"}
    }
)
async def lint_python_code(req: PythonLintRequest):
    """
    Lint Python source code using ruff.
    
    This endpoint provides standalone Python code linting functionality
    without any code modification or telemetry injection.
    
    Args:
        req: Linting request containing Python source code
        
    Returns:
        PythonLintResponse: Linting results with pass/fail status and error messages
        
    Raises:
        HTTPException: For various linting errors with appropriate status codes
    """
    try:
        service = SourceCodeConversionService()
        passed, errors, warnings = service.lint_python_code(req.source_code)
        
        return PythonLintResponse(
            passed=passed,
            errors=errors,
            warnings=warnings
        )
        
    except InvalidSourceError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    except LintError as e:
        raise HTTPException(status_code=422, detail=str(e))
        
    except Exception as e:
        logger.exception("Unexpected error in Python linting")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/lint/javascript", 
    response_model=JavaScriptLintResponse,
    summary="Lint JavaScript Code",
    description="""
    Lint JavaScript source code using ESLint for comprehensive code analysis.
    
    This endpoint provides standalone JavaScript code linting functionality
    without any code modification or telemetry injection. Uses ESLint
    with modern JavaScript and TypeScript support.
    
    **Linting Capabilities:**
    - **Syntax Validation**: ES6+ syntax checking
    - **Style Guide**: Airbnb, Standard, or custom rules
    - **Security Analysis**: XSS and injection vulnerability detection
    - **Accessibility**: ARIA and accessibility guidelines
    - **Best Practices**: Modern JavaScript patterns
    
    **ESLint Configuration:**
    - Configurable rule sets and presets
    - Plugin ecosystem support
    - Automatic fixing capabilities
    - Framework-specific rules (React, Vue, etc.)
    - TypeScript support with @typescript-eslint
    
    **Issue Detection:**
    - **Syntax Errors**: Invalid JavaScript syntax
    - **Style Violations**: Code formatting and style issues
    - **Potential Bugs**: Runtime error patterns
    - **Security Issues**: Vulnerabilities and risks
    - **Performance**: Optimization opportunities
    
    **Use Cases:**
    - Pre-deployment code validation
    - Code review automation
    - Team coding standard enforcement
    - Technical debt identification
    - Educational feedback for developers
    
    **Parameters:**
    - **source_code**: JavaScript/TypeScript code to analyze
    - **config**: Optional ESLint configuration
    - **parser**: Specify parser (babel, typescript, etc.)
    - **env**: Target environment (browser, node, etc.)
    
    **Flow:**
    1. Parse JavaScript/TypeScript source code
    2. Apply ESLint rules and plugins
    3. Analyze for syntax, style, and security issues
    4. Categorize issues by severity and type
    5. Generate fix suggestions
    6. Return comprehensive linting report
    
    **Response Format:**
    Returns pass/fail status with detailed issue information
    including line numbers, rule names, and auto-fix suggestions.
    """,
    responses={
        200: {
            "description": "JavaScript code linted successfully",
            "content": {
                "application/json": {
                    "example": {
                        "passed": False,
                        "errors": [
                            {
                                "line": 23,
                                "column": 5,
                                "message": "'console.log' is not allowed",
                                "rule": "no-console",
                                "severity": "error",
                                "fix_suggestion": "Use proper logging mechanism"
                            }
                        ],
                        "warnings": [
                            {
                                "line": 10,
                                "column": 15,
                                "message": "Missing semicolon",
                                "rule": "semi",
                                "severity": "warning",
                                "auto_fixable": True
                            }
                        ]
                    }
                }
            }
        },
        400: {"description": "Invalid JavaScript source code"},
        422: {"description": "Code linting errors found"},
        500: {"description": "Linting processing failed"}
    }
)
async def lint_javascript_code(req: JavaScriptLintRequest):
    """
    Lint JavaScript source code using ESLint.
    
    This endpoint provides standalone JavaScript code linting functionality
    without any code modification or telemetry injection.
    
    Args:
        req: Linting request containing JavaScript source code
        
    Returns:
        JavaScriptLintResponse: Linting results with pass/fail status and error messages
        
    Raises:
        HTTPException: For various linting errors with appropriate status codes
    """
    try:
        service = SourceCodeConversionService()
        passed, errors, warnings = service.lint_javascript_code(req.source_code)
        
        return JavaScriptLintResponse(
            passed=passed,
            errors=errors,
            warnings=warnings
        )
        
    except InvalidSourceError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    except LintError as e:
        raise HTTPException(status_code=422, detail=str(e))
        
    except Exception as e:
        logger.exception("Unexpected error in JavaScript linting")
        raise HTTPException(status_code=500, detail="Internal server error")
