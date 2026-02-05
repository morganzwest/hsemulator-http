import base64
import logging
from uuid import UUID
from typing import Optional
from app.db import get_supabase
from app.models.errors import SecretPersistenceError
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def encode_bytea_hex(data: bytes) -> str:
    # PostgREST bytea input format
    return "\\x" + data.hex()


def insert_secret(
    *,
    scope: str,
    portal_id: UUID,
    action_id: Optional[UUID],
    name: str,
    ciphertext: bytes,
    nonce: bytes,
    dek_wrapped: bytes,
    dek_nonce: bytes,
    aad: dict,
    kek_key_id: str,
    created_by: Optional[UUID],
) -> UUID:
    supabase = get_supabase()

    payload = {
        "scope": scope,
        "portal_id": str(portal_id),
        "name": name,

        # IMPORTANT: store as bytea-hex, not base64
        "ciphertext": encode_bytea_hex(ciphertext),
        "nonce": encode_bytea_hex(nonce),
        "dek_wrapped": encode_bytea_hex(dek_wrapped),
        "dek_nonce": encode_bytea_hex(dek_nonce),

        "aad": aad,
        "kek_key_id": kek_key_id,
    }

    if action_id is not None:
        payload["action_id"] = str(action_id)

    if created_by is not None:
        payload["created_by"] = str(created_by)

    try:
        result = supabase.table("secrets").insert(payload).execute()

        if not result.data or not isinstance(result.data, list):
            raise SecretPersistenceError(
                "Secret insert succeeded but no ID was returned")

        return UUID(result.data[0]["id"])

    except SecretPersistenceError:
        raise

    except Exception:
        logger.exception(
            "Failed to insert secret",
            extra={
                "portal_id": str(portal_id),
                "action_id": str(action_id) if action_id else None,
                "scope": scope,
                "name": name,
            },
        )
        raise SecretPersistenceError("Failed to insert secret")


def get_secret_by_id(secret_id: UUID) -> dict:
    supabase = get_supabase()

    try:
        result = (
            supabase
            .table("secrets")
            .select(
                "id, scope, portal_id, action_id, name, "
                "ciphertext, nonce, dek_wrapped, dek_nonce, aad, kek_key_id, "
                "created_at, created_by"
            )
            .eq("id", str(secret_id))
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Secret not found")

        
        return result.data[0]

    except HTTPException:
        raise

    except SecretPersistenceError:
        raise

    except Exception:
        logger.exception(
            "Failed to fetch secret",
            extra={"secret_id": str(secret_id)},
        )
        raise SecretPersistenceError("Failed to fetch secret")



def update_secret_value(
    *,
    secret_id: UUID,
    ciphertext: bytes,
    nonce: bytes,
    dek_wrapped: bytes,
    dek_nonce: bytes,
    aad: dict,
    kek_key_id: str,
) -> None:
    supabase = get_supabase()

    payload = {
        "ciphertext": encode_bytea_hex(ciphertext),
        "nonce": encode_bytea_hex(nonce),
        "dek_wrapped": encode_bytea_hex(dek_wrapped),
        "dek_nonce": encode_bytea_hex(dek_nonce),
        "aad": aad,
        "kek_key_id": kek_key_id,
    }

    try:
        result = (
            supabase
            .table("secrets")
            .update(payload)
            .eq("id", str(secret_id))
            .execute()
        )

        if not result.data:
            raise SecretPersistenceError("Secret not found")

    except SecretPersistenceError:
        raise

    except Exception:
        logger.exception(
            "Failed to update secret value",
            extra={"secret_id": str(secret_id)},
        )
        raise SecretPersistenceError("Failed to update secret")


def delete_secret_record(*, secret_id: UUID) -> None:
    supabase = get_supabase()

    try:
        result = (
            supabase
            .table("secrets")
            .delete()
            .eq("id", str(secret_id))
            .execute()
        )

        if not result.data:
            raise SecretPersistenceError("Secret not found")

    except SecretPersistenceError:
        raise

    except Exception:
        logger.exception(
            "Failed to delete secret",
            extra={"secret_id": str(secret_id)},
        )
        raise SecretPersistenceError("Failed to delete secret")

def get_portal_owner_profile_ids(*, portal_id: UUID) -> list[UUID]:
    supabase = get_supabase()

    try:
        result = (
            supabase
            .table("profiles")
            .select("id")
            .contains("portal_uuids", [str(portal_id)])
            .execute()
        )

        return [UUID(row["id"]) for row in (result.data or [])]

    except Exception:
        logger.exception(
            "Failed to fetch portal owners",
            extra={"portal_id": str(portal_id)},
        )
        raise SecretPersistenceError("Failed to fetch portal owners")

