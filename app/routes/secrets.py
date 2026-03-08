"""
Secret management endpoints.

This blueprint handles CRUD operations for encrypted secrets
including creation, updates, and deletion.
"""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from app.auth import require_runtime_token
from app.models.secrets import (
    CreateSecretRequest,
    CreateSecretResponse,
    UpdateSecretRequest,
    UpdateSecretResponse,
    DeleteSecretResponse,
    DeleteSecretRequest
)
from app.services.secret_service import create_secret, update_secret, delete_secret
from app.models.errors import (
    SecretPersistenceError,
    SecretPortalMismatchError,
    SecretForbiddenError,
    SecretNotFoundError,
    CicdSecretValidationError,
    CicdTokenInvalidError,
    CicdTokenMissingScopesError,
    SecretAlreadyExistsError,
)

router = APIRouter(
    prefix="/secrets",
    tags=["Secret Management"],
    responses={
        401: {"description": "Unauthorized - Invalid or missing authentication token"},
        403: {"description": "Forbidden - Insufficient permissions"},
        404: {"description": "Secret not found"},
        409: {"description": "Conflict - Secret already exists"},
        422: {"description": "Unprocessable Entity - Validation error"},
        500: {"description": "Internal server error"}
    }
)


@router.post(
    "",
    response_model=CreateSecretResponse,
    dependencies=[Depends(require_runtime_token)],
    summary="Create Secret",
    description="""
    Create a new encrypted secret with AES-GCM encryption.
    
    This endpoint creates a new secret that is securely encrypted and stored
    in the database. Each secret is encrypted with a unique data encryption key (DEK)
    that is wrapped using the key encryption key (KEK) for maximum security.
    
    **Security Features:**
    - AES-GCM encryption for confidentiality and integrity
    - Unique DEK per secret for key isolation
    - KEK wrapping for key management
    - HubSpot token validation for CICD-scoped secrets
    
    **Secret Scopes:**
    - **CICD**: For HubSpot workflow automation tokens
    - **Action**: For individual workflow action secrets
    - **Portal**: For portal-wide shared secrets
    
    **CICD Token Validation:**
    For CICD-scoped secrets, the endpoint validates HubSpot API permissions:
    - Tests access to automation/v4/flows endpoint
    - Validates required OAuth scopes
    - Returns specific error codes for different failure scenarios
    
    **Flow:**
    1. Validate request parameters and authentication
    2. For CICD secrets: validate HubSpot token and scopes
    3. Generate unique DEK and encrypt secret value
    4. Wrap DEK with KEK and store in database
    5. Return secret ID for future reference
    """,
    responses={
        201: {
            "description": "Secret created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "secret_id": "550e8400-e29b-41d4-a716-446655440000"
                    }
                }
            }
        },
        400: {"description": "Invalid request parameters or CICD validation failed"},
        401: {"description": "HubSpot token is invalid or expired (CICD secrets only)"},
        403: {"description": "HubSpot token lacks required scopes (CICD secrets only)"},
        409: {"description": "Secret with same name already exists for this scope"},
        500: {"description": "Database encryption or persistence error"}
    }
)
async def create_secret_endpoint(req: CreateSecretRequest):
    """
    Create a new encrypted secret.

    This endpoint creates a new secret with AES-GCM encryption and stores it
    securely in the database. The secret is encrypted with a unique data
    encryption key (DEK) that is wrapped using the key encryption key (KEK).

    For CICD-scoped secrets, this endpoint validates that the token has the
    required HubSpot API permissions before storing the secret in the database.
    The validation makes a test API call to HubSpot's automation/v4/flows endpoint
    and returns appropriate error messages for different failure scenarios:

    - 401: Token is invalid or expired
    - 403: Token lacks required HubSpot API scopes
    - 200: Token is valid with proper scopes

    Args:
        req: Secret creation request containing scope, portal ID, name, and value

    Returns:
        CreateSecretResponse: Confirmation of secret creation with generated ID

    Raises:
        HTTPException: For various validation and persistence errors with appropriate status codes
    """
    try:
        secret_id = await create_secret(
            scope=req.scope,
            portal_id=req.portal_id,
            action_id=req.action_id,
            name=req.name,
            value=req.value,
            created_by=req.created_by,
        )
        return CreateSecretResponse(ok=True, secret_id=secret_id)

    except CicdTokenInvalidError as e:
        # Token is invalid/expired (401)
        raise HTTPException(status_code=401, detail=str(e))

    except CicdTokenMissingScopesError as e:
        # Token lacks required scopes (403)
        raise HTTPException(status_code=403, detail=str(e))

    except CicdSecretValidationError as e:
        # General CICD validation error (400)
        raise HTTPException(status_code=400, detail=str(e))

    except SecretAlreadyExistsError as e:
        # Secret already exists (409)
        raise HTTPException(status_code=409, detail=str(e))

    except (SecretPersistenceError, RuntimeError) as e:
        # Database or other persistence errors (500)
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/{secret_id}",
    response_model=UpdateSecretResponse,
    dependencies=[Depends(require_runtime_token)],
    summary="Update Secret",
    description="""
    Update an existing secret's value with fresh encryption.
    
    This endpoint updates the value of an existing secret while maintaining
    the same metadata (scope, name, portal ID, etc.). The new value is
    encrypted with a fresh data encryption key for enhanced security.
    
    **Security Features:**
    - Generates new DEK for each update (key rotation)
    - Maintains secret metadata for audit trail
    - Atomic update operation to prevent partial states
    - Authorization checks before modification
    
    **Use Cases:**
    - Rotating expired API keys or tokens
    - Updating configuration values
    - Refreshing compromised credentials
    - Regular secret rotation schedules
    
    **Flow:**
    1. Validate secret ID and authentication
    2. Verify user has permission to modify this secret
    3. Generate new DEK and encrypt updated value
    4. Update secret record atomically
    5. Return confirmation with secret ID
    """,
    responses={
        200: {
            "description": "Secret updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "secret_id": "550e8400-e29b-41d4-a716-446655440000"
                    }
                }
            }
        },
        401: {"description": "Unauthorized - Invalid or missing authentication token"},
        404: {"description": "Secret not found"},
        500: {"description": "Encryption or database update error"}
    }
)
def update_secret_endpoint(secret_id: UUID, req: UpdateSecretRequest):
    """
    Update an existing secret's value.

    This endpoint updates the value of an existing secret while maintaining
    the same metadata (scope, name, etc.). The new value is encrypted with
    a fresh data encryption key for security.

    Args:
        secret_id: UUID of the secret to update
        req: Update request containing the new secret value

    Returns:
        UpdateSecretResponse: Confirmation of successful update
    """
    update_secret(secret_id=secret_id, value=req.value)
    return UpdateSecretResponse(ok=True, secret_id=secret_id)


@router.delete(
    "/{secret_id}",
    response_model=DeleteSecretResponse,
    dependencies=[Depends(require_runtime_token)],
    summary="Delete Secret",
    description="""
    Delete an existing secret with authorization validation.
    
    This endpoint permanently deletes a secret after performing comprehensive
    authorization checks to ensure the user has permission to delete secrets
    from the specified portal and scope.
    
    **Security Features:**
    - Portal ownership verification
    - User authorization validation
    - Scope-based access control
    - Secure deletion with audit trail
    
    **Authorization Checks:**
    - User must be the secret creator or portal admin
    - Portal ID must match the secret's portal
    - Valid authentication token required
    - Proper scope permissions verified
    
    **Use Cases:**
    - Removing deprecated secrets
    - Cleaning up unused credentials
    - Revoking compromised access
    - Secret lifecycle management
    
    **Flow:**
    1. Validate secret ID and authentication
    2. Verify portal ownership and user permissions
    3. Check scope-based access rights
    4. Perform secure deletion
    5. Return confirmation with deleted secret ID
    
    ⚠️ **Warning:** This operation is irreversible. Deleted secrets cannot be recovered.
    """,
    responses={
        200: {
            "description": "Secret deleted successfully",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "secret_id": "550e8400-e29b-41d4-a716-446655440000"
                    }
                }
            }
        },
        401: {"description": "Unauthorized - Invalid or missing authentication token"},
        403: {"description": "Forbidden - Insufficient permissions to delete this secret"},
        404: {"description": "Secret not found"},
        500: {"description": "Database deletion error"}
    }
)
def delete_secret_endpoint(secret_id: UUID, req: DeleteSecretRequest):
    """
    Delete an existing secret.

    This endpoint deletes a secret after performing authorization checks
    to ensure the user has permission to delete secrets from the specified portal.

    Args:
        secret_id: UUID of the secret to delete
        req: Delete request containing portal ID and user ID for authorization

    Returns:
        DeleteSecretResponse: Confirmation of successful deletion

    Raises:
        HTTPException: If authorization fails or secret is not found
    """
    try:
        delete_secret(
            secret_id=secret_id,
            portal_id=req.portal_id,
            user_id=req.user_id
        )
        return DeleteSecretResponse(ok=True, secret_id=secret_id)

    except (SecretNotFoundError, SecretPortalMismatchError, SecretForbiddenError) as e:
        # Use default status code if exception doesn't have status_code attribute
        status_code = getattr(e, 'status_code', 404)
        raise HTTPException(status_code=status_code, detail=str(e))

    except SecretPersistenceError as e:
        # SecretPersistenceError should have status_code from base class
        status_code = getattr(e, 'status_code', 500)
        raise HTTPException(status_code=status_code, detail=str(e))
