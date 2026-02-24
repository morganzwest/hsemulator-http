"""
CICD Secret Validation Service for HSEmulator

This module provides validation functionality for CICD-scoped secrets to ensure
they have the required HubSpot API permissions before being stored in the database.

Validation Process:
- Makes a test API call to HubSpot's automation/v4/flows endpoint
- Interprets HTTP response codes to determine token validity and scope permissions
- Raises specific exceptions for different failure scenarios

Error Handling:
- 401: Token is invalid/expired
- 403: Token is valid but lacks required scopes
- Other errors: General validation failures
"""

import logging
from typing import Dict, Any

import httpx

from app.models.errors import (
    CicdSecretValidationError,
    CicdTokenInvalidError,
    CicdTokenMissingScopesError,
)

logger = logging.getLogger(__name__)

HUBSPOT_BASE_URL = "https://api.hubapi.com"


async def validate_cicd_token_scopes(token: str) -> Dict[str, Any]:
    """
    Validate that a CICD token has the required HubSpot API scopes.
    
    This function makes a test API call to the HubSpot automation flows endpoint
    to verify that the token is valid and has the necessary permissions for
    CICD operations.
    
    Args:
        token: HubSpot API token to validate
        
    Returns:
        Dict containing validation response data for logging/debugging
        
    Raises:
        CicdTokenInvalidError: If token is invalid or expired (401 response)
        CicdTokenMissingScopesError: If token lacks required scopes (403 response)
        CicdSecretValidationError: For other validation failures
        
    Example:
        >>> try:
        ...     result = await validate_cicd_token_scopes("pat_token")
        ...     print("Token is valid with proper scopes")
        ... except CicdTokenInvalidError:
        ...     print("Token is invalid")
        ... except CicdTokenMissingScopesError:
        ...     print("Token lacks required scopes")
    """
    # Validate input
    if not token or not token.strip():
        logger.warning("CICD token validation failed: empty token provided")
        raise CicdTokenInvalidError(
            "Invalid CICD token: token cannot be empty"
        )
    
    token = token.strip()
    
    url = f"{HUBSPOT_BASE_URL}/automation/v4/flows"
    params = {"limit": "1"}  # Minimize data transfer, just testing access
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    logger.info("Validating CICD token scopes", extra={
        "url": url,
        "params": params
    })
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            
            logger.info("CICD token validation response", extra={
                "status_code": response.status_code,
                "response_headers": dict(response.headers)
            })
            
            # Handle different response scenarios
            if response.status_code == 200:
                logger.info("CICD token validation successful: token has required scopes")
                return {
                    "status": "valid",
                    "status_code": response.status_code,
                    "message": "Token has required HubSpot API scopes"
                }
            
            elif response.status_code == 401:
                logger.warning("CICD token validation failed: invalid token (401)")
                raise CicdTokenInvalidError(
                    f"Invalid CICD token: authentication failed (401). "
                    "Please check that the token is correct and not expired."
                )
            
            elif response.status_code == 403:
                logger.warning("CICD token validation failed: missing scopes (403)")
                raise CicdTokenMissingScopesError(
                    f"CICD token missing required HubSpot API scopes (403). "
                    "Please ensure the token has the necessary automation/flows permissions."
                )
            
            else:
                # Handle unexpected status codes
                error_detail = f"Unexpected response from HubSpot API: {response.status_code}"
                if response.text:
                    error_detail += f" - {response.text}"
                
                logger.error("CICD token validation failed: unexpected response", extra={
                    "status_code": response.status_code,
                    "response_text": response.text
                })
                
                raise CicdSecretValidationError(error_detail)
    
    except (CicdTokenInvalidError, CicdTokenMissingScopesError, CicdSecretValidationError):
        # Re-raise our own exceptions
        raise
    
    except httpx.TimeoutException:
        logger.error("CICD token validation failed: request timeout")
        raise CicdSecretValidationError(
            "Token validation failed: request timeout. Please try again."
        )
    
    except httpx.NetworkError as e:
        logger.error("CICD token validation failed: network error", extra={
            "error": str(e)
        })
        raise CicdSecretValidationError(
            f"Token validation failed: network error - {str(e)}"
        )
    
    except httpx.HTTPStatusError as e:
        logger.error("CICD token validation failed: HTTP error", extra={
            "status_code": e.response.status_code,
            "response_text": e.response.text
        })
        raise CicdSecretValidationError(
            f"Token validation failed: HTTP error {e.response.status_code}"
        )
    
    except Exception as e:
        logger.exception("CICD token validation failed: unexpected error")
        raise CicdSecretValidationError(
            f"Token validation failed: unexpected error - {str(e)}"
        )
