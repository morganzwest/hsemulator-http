import logging
from uuid import UUID
from typing import Optional

from app.utils.crypto import encrypt_secret
from app.db.secrets import insert_secret, update_secret_value, get_secret_by_id, delete_secret_record, get_portal_owner_profile_ids
from app.models.errors import (
    SecretAlreadyExistsError,
    SecretPersistenceError,
)
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def create_secret(
    *,
    scope: str,
    portal_id: UUID,
    action_id: Optional[UUID],
    name: str,
    value: str,
    created_by: Optional[UUID],
) -> UUID:
    try:
        encrypted = encrypt_secret(
            plaintext=value,
            portal_id=str(portal_id),
            name=name,
            scope=scope,
            action_id=str(action_id) if action_id else None,
        )

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
                "name": name,
            },
        )
        raise SecretPersistenceError("Unhandled error during secret creation")


def update_secret(
    *,
    secret_id: UUID,
    value: str,
) -> None:
    try:
        record = get_secret_by_id(secret_id)

        encrypted = encrypt_secret(
            plaintext=value,
            portal_id=str(record["portal_id"]),
            name=record["name"],
            scope=record["scope"],
            action_id=str(record["action_id"]) if record.get(
                "action_id") else None,
        )

        update_secret_value(
            secret_id=secret_id,
            ciphertext=encrypted["ciphertext"],
            nonce=encrypted["nonce"],
            dek_wrapped=encrypted["dek_wrapped"],
            dek_nonce=encrypted["dek_nonce"],
            aad=encrypted["aad"],
            kek_key_id=encrypted["kek_key_id"],
        )

    except SecretPersistenceError:
        raise

    except Exception:
        logger.exception(
            "Unhandled error during secret update",
            extra={"secret_id": str(secret_id)},
        )
        raise SecretPersistenceError("Unhandled error during secret update")


def delete_secret(*, secret_id: UUID) -> None:
    try:
        get_secret_by_id(secret_id)

        delete_secret_record(secret_id=secret_id)

    except SecretPersistenceError:
        raise

    except Exception:
        logger.exception(
            "Unhandled error during secret delete",
            extra={"secret_id": str(secret_id)},
        )
        raise SecretPersistenceError("Unhandled error during secret delete")
    

def delete_secret(*, secret_id: UUID, portal_id: UUID, user_id: UUID) -> None:
    try:
        secret = get_secret_by_id(secret_id)  # ideally raises SecretPersistenceError("Secret not found")
    except KeyError:
        # only needed if get_secret_by_id currently raises KeyError
        raise SecretPersistenceError("Secret not found")

    if str(secret["portal_id"]) != str(portal_id):
        raise HTTPException(status_code=401, detail="Portal mismatch")

    owner_ids = get_portal_owner_profile_ids(portal_id=portal_id)
    if user_id not in owner_ids:
        raise HTTPException(status_code=403, detail="Forbidden")

    delete_secret_record(secret_id=secret_id)
