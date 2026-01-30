import base64
import logging
from uuid import UUID
from typing import Optional
from app.db import get_supabase
from app.models.errors import SecretPersistenceError

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

    result = (
        supabase
        .table("secrets")
        .select(
            "id, scope, portal_id, action_id, name, "
            "ciphertext, nonce, dek_wrapped, dek_nonce, aad, kek_key_id, "
            "created_at, created_by"
        )
        .eq("id", str(secret_id))
        .single()
        .execute()
    )

    if not result.data:
        raise KeyError("Secret not found")

    return result.data


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
