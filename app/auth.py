"""
Authentication Module for HSEmulator HTTP Service

This module provides authentication and authorization functionality for the API.
It implements Bearer token authentication using a runtime API token configured
via environment variables.

Security Features:
- Bearer token authentication scheme
- Configuration validation for runtime tokens
- HTTP status code compliance for authentication errors
- Protection against missing or invalid authentication headers

Usage:
- Add `dependencies=[Depends(require_runtime_token)]` to endpoints that require authentication
- Configure RUNTIME_API_TOKEN environment variable with a secure token
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings

# Initialize HTTP Bearer security scheme (auto_error=False for custom handling)
security = HTTPBearer(auto_error=False)


def require_runtime_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Dependency function to require valid runtime API token authentication.

    This function validates that a valid Bearer token is present in the Authorization
    header and matches the configured runtime API token. It raises appropriate
    HTTP exceptions for missing or invalid authentication.

    Args:
        credentials: HTTP Authorization credentials extracted from request header

    Returns:
        bool: True if authentication is successful

    Raises:
        RuntimeError: If RUNTIME_API_TOKEN is not configured
        HTTPException: If authentication fails (401 for missing/invalid, 403 for wrong token)
    """
    # Ensure runtime token is configured
    if settings.runtime_api_token is None:
        raise RuntimeError("RUNTIME_API_TOKEN not configured")

    # Check if Authorization header is present
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    # Validate Bearer token scheme
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid auth scheme",
        )

    # Validate token against configured runtime token
    if credentials.credentials != settings.runtime_api_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid token",
        )

    return True
