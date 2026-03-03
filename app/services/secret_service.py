"""
Secret Management Service for Novocode Runtime

This module provides secure secret storage and management functionality using
AES-GCM encryption with a key-wrapping pattern. It handles the creation,
update, and deletion of secrets while maintaining security best practices.

Security Architecture:
- AES-GCM authenticated encryption for confidentiality and integrity
- Key Encryption Key (KEK) wraps Data Encryption Keys (DEK)
- Additional Authenticated Data (AAD) binds secrets to their context
- Per-secret unique DEKs for key isolation

Secret Scopes:
- portal: Portal-wide secrets shared across actions
- action: Action-specific secrets for individual workflows
- cicd: CI/CD secrets for HubSpot API integration

Error Handling:
- Comprehensive error classification and logging
- Secure error messages that don't leak sensitive data
- Transactional operations for data consistency
"""

import logging
from uuid import UUID
from typing import Optional

from app.utils.crypto import encrypt_secret
from app.db.secrets import insert_secret, update_secret_value, get_secret_by_id, delete_secret_record, get_portal_owner_profile_ids
from app.models.errors import (
    SecretAlreadyExistsError,
    SecretPersistenceError,
    SecretNotFoundError,
    SecretPortalMismatchError,
    SecretForbiddenError,
    CicdSecretValidationError,
    CicdTokenInvalidError,
    CicdTokenMissingScopesError,
)
from app.services.cicd_secret_validation_service import validate_cicd_token_scopes
from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def create_secret(
    *,
    scope: str,
    portal_id: UUID,
    action_id: Optional[UUID],
    name: str,
    value: str,
    created_by: Optional[UUID],
) -> UUID:
    """
    Create a new encrypted secret with AES-GCM encryption.

    This function encrypts the secret value using a unique data encryption key
    (DEK) that is wrapped with the key encryption key (KEK). For CICD-scoped
    secrets, it validates the token has required HubSpot API permissions before
    storing in the database.

    Args:
        scope: Secret scope ('portal', 'action', or 'cicd')
        portal_id: UUID of the portal the secret belongs to
        action_id: Optional UUID of the specific action (for action-scoped secrets)
        name: Human-readable name for the secret
        value: Plain text secret value to be encrypted
        created_by: Optional UUID of the user creating the secret

    Returns:
        UUID: The unique identifier of the created secret

    Raises:
        SecretAlreadyExistsError: If a secret with the same context already exists
        SecretPersistenceError: If database operations fail
        CicdTokenInvalidError: If CICD token is invalid (401 response)
        CicdTokenMissingScopesError: If CICD token lacks required scopes (403 response)
        CicdSecretValidationError: For other CICD validation failures
        RuntimeError: For unexpected encryption or programming errors
    """
    try:
        # Validate CICD token scopes before proceeding with CICD secrets
        if scope == "cicd":
            logger.info("Validating CICD token scopes before secret creation", extra={
                "portal_id": str(portal_id),
                "secret_name": name,
                "scope": scope
            })

            # Validate the token has required HubSpot API scopes
            await validate_cicd_token_scopes(value)

            logger.info(
                "CICD token validation successful, proceeding with secret creation")

        # Encrypt the secret value with AES-GCM and key wrapping
        encrypted = encrypt_secret(
            plaintext=value,
            portal_id=str(portal_id),
            name=name,
            scope=scope,
            action_id=str(action_id) if action_id else None,
        )

        # Store the encrypted secret in the database
        return insert_secret(
            scope=scope,
            portal_id=portal_id,
            action_id=action_id,
            name=name,
            ciphertext=encrypted["ciphertext"],
            nonce=encrypted["nonce"],
            dek_wrapped=encrypted["dek_wrapped"],
            dek_nonce=encrypted["dek_nonce"],
            aad=encrypted["aad"],
            kek_key_id=encrypted["kek_key_id"],
            created_by=created_by,
        )

    except (CicdSecretValidationError, CicdTokenInvalidError, CicdTokenMissingScopesError):
        # Re-raise CICD validation errors cleanly
        raise

    except SecretAlreadyExistsError:
        # Bubble up cleanly — already correct HTTP semantics
        raise

    except SecretPersistenceError:
        # Already logged at DB layer
        raise

    except Exception:
        # Truly unexpected failure (crypto, programming error, etc.)
        logger.exception(
            "Unhandled error during secret creation",
            extra={
                "portal_id": str(portal_id),
                "action_id": str(action_id) if action_id else None,
                "scope": scope,
                "secret_name": name,
            },
        )
        raise SecretPersistenceError("Unhandled error during secret creation")


def update_secret(
    *,
    secret_id: UUID,
    value: str,
) -> None:
    """
    Update an existing secret's value with fresh encryption.

    This function retrieves the existing secret metadata, encrypts the new value
    with a fresh data encryption key (DEK) for security, and updates the
    stored encrypted data. The secret's context (scope, name, etc.) remains
    unchanged.

    Args:
        secret_id: UUID of the secret to update
        value: New plain text secret value to encrypt and store

    Raises:
        SecretNotFoundError: If the secret does not exist
        SecretPersistenceError: If database operations fail
        RuntimeError: For unexpected encryption or programming errors
    """
    try:
        # Retrieve existing secret to maintain context metadata
        record = get_secret_by_id(secret_id)

        # Encrypt new value with fresh DEK for security
        encrypted = encrypt_secret(
            plaintext=value,
            portal_id=str(record["portal_id"]),
            name=record["name"],
            scope=record["scope"],
            action_id=str(record["action_id"]) if record.get(
                "action_id") else None,
        )

        # Update secret with new encrypted data
        update_secret_value(
            secret_id=secret_id,
            ciphertext=encrypted["ciphertext"],
            nonce=encrypted["nonce"],
            dek_wrapped=encrypted["dek_wrapped"],
            dek_nonce=encrypted["dek_nonce"],
            aad=encrypted["aad"],
            kek_key_id=encrypted["kek_key_id"],
        )

    except Exception:
        logger.exception(
            "Unhandled error during secret update",
            extra={"secret_id": str(secret_id)},
        )
        raise SecretPersistenceError("Unhandled error during secret update")


def delete_secret(*, secret_id: UUID, portal_id: UUID, user_id: UUID) -> None:
    """
    Delete a secret with comprehensive authorization validation.

    This function performs layered security checks before deletion to ensure
    only authorized users can delete secrets from their portals. It validates
    secret existence, portal ownership, and user permissions before proceeding
    with the deletion.

    Authorization Flow:
    1. Verify the secret exists in the database
    2. Confirm the provided portal_id matches the secret's portal_id
    3. Validate the user_id belongs to an owner of the portal
    4. Proceed with deletion if all checks pass

    Args:
        secret_id: UUID of the secret to delete
        portal_id: UUID of the portal (for authorization validation)
        user_id: UUID of the user requesting deletion

    Raises:
        HTTPException: If portal doesn't match or user is not authorized
        SecretNotFoundError: If the secret does not exist
        SecretPortalMismatchError: If portal_id doesn't match secret's portal
        SecretForbiddenError: If user is not a portal owner
        SecretPersistenceError: If database operations fail
    """

    try:
        # Retrieve secret for validation
        secret = get_secret_by_id(secret_id)

        # Validate portal ownership - prevent cross-portal access
        if str(secret["portal_id"]) != str(portal_id):
            raise SecretPortalMismatchError()

        # Get portal owners and validate user authorization
        owner_ids = get_portal_owner_profile_ids(portal_id=portal_id)
        if user_id not in owner_ids:
            raise SecretForbiddenError(
                "Forbidden: User is not an owner of the portal")

        # Perform the deletion
        delete_secret_record(secret_id=secret_id)

    except HTTPException:
        # Re-raise HTTP exceptions (authorization errors)
        raise

    except SecretPersistenceError:
        # Re-raise persistence errors (including "Secret not found")
        raise

    except Exception:
        # Catch-all for other unexpected errors
        logger.exception(
            "Unexpected error during secret deletion",
            extra={
                "secret_id": str(secret_id),
                "portal_id": str(portal_id),
                "user_id": str(user_id),
            },
        )
        raise SecretPersistenceError("Failed to delete secret")
