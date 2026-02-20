"""
Secret Decryption Service

This module provides functionality for decrypting stored secrets using authenticated encryption.
It handles the construction of Additional Authenticated Data (AAD) and provides a secure
interface for testing secret decryption capabilities.

The service uses AES-GCM encryption with key encryption keys (KEK) and data encryption keys (DEK)
following a key-wrapping pattern for secure secret storage and retrieval.
"""

import logging
from uuid import UUID
from cryptography.exceptions import InvalidTag

from app.db.secrets import get_secret_by_id
from app.utils.crypto import decrypt_secret, canonical_aad
from app.models.errors import SecretPersistenceError

logger = logging.getLogger(__name__)


def build_aad_from_record(record: dict) -> dict:
    """
    Build Additional Authenticated Data (AAD) from a secret record.

    AAD is used in AES-GCM encryption to bind the ciphertext to the context
    in which it was created, preventing ciphertext replay attacks across
    different contexts.

    Args:
        record (dict): Secret record containing at minimum:
            - portal_id: The portal identifier
            - scope: The scope/context of the secret
            - name: The name of the secret
            - action_id (optional): Action identifier for action-specific secrets

    Returns:
        dict: Canonical AAD structure with version and context fields
    """
    aad = {
        "v": 1,  # Version of the AAD format
        "portal_id": record["portal_id"],
        "scope": record["scope"],
        "name": record["name"],
    }

    # Include action_id only if present (optional field for action-scoped secrets)
    if record.get("action_id"):
        aad["action_id"] = record["action_id"]

    return aad


def decrypt_secret_for_test(secret_id: UUID) -> dict:
    """
    Decrypt a secret for testing purposes.

    This function retrieves an encrypted secret from database and attempts
    to decrypt it using the stored cryptographic material and context. It's
    primarily intended for testing and validation of secret storage.

    The decryption process uses:
    - AES-GCM for authenticated encryption
    - Key wrapping pattern with KEK/DEK
    - Additional Authenticated Data for context binding

    Args:
        secret_id (UUID): The unique identifier of secret to decrypt

    Returns:
        dict: Decrypted secret information containing:
            - id: Secret identifier
            - scope: Secret scope/context
            - portal_id: Portal identifier
            - action_id: Action identifier (if applicable)
            - name: Secret name
            - value: The decrypted secret value
            - kek_key_id: Key encryption key identifier
            - created_at: Creation timestamp
            - created_by: Creator identifier (if available)

    Raises:
        SecretPersistenceError: When secret is not found or decryption fails
        InvalidTag: When authentication tag verification fails (handled internally)
    """
    record = None
    try:
        # Retrieve the encrypted secret record from database
        record = get_secret_by_id(secret_id)

        # Build AAD from the record to ensure context binding during decryption
        aad = build_aad_from_record(record)

        # Perform the actual decryption using the cryptographic utility
        value = decrypt_secret(
            ciphertext_b64=record["ciphertext"],
            nonce_b64=record["nonce"],
            dek_wrapped_b64=record["dek_wrapped"],
            dek_nonce_b64=record["dek_nonce"],
            portal_id=record["portal_id"],
            aad=aad,
        )

        # Return the decrypted secret with metadata
        return {
            "id": record["id"],
            "scope": record["scope"],
            "portal_id": record["portal_id"],
            "action_id": record.get("action_id"),
            "name": record["name"],
            "value": value,  # The decrypted secret value
            "kek_key_id": record["kek_key_id"],
            "created_at": record["created_at"],
            "created_by": record.get("created_by"),
        }

    except KeyError:
        # Secret record not found or missing required fields
        raise SecretPersistenceError("Secret not found")

    except InvalidTag:
        # Authentication tag verification failed - indicates tampering or corruption
        # Log detailed error for debugging without exposing sensitive data
        logger.error(
            "Test decryption failed: InvalidTag",
            extra={
                "secret_id": str(secret_id),
                "portal_id": str(record.get("portal_id")) if record else None,
                "scope": record.get("scope") if record else None,
                "secret_name": record.get("name") if record else None,
            },
        )
        raise SecretPersistenceError("Failed to decrypt secret (InvalidTag)")

    except Exception:
        # Catch-all for other unexpected errors during decryption
        logger.exception(
            "Test decryption failed",
            extra={"secret_id": str(secret_id)},
        )
        raise SecretPersistenceError("Failed to decrypt secret")
