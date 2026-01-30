# services/secret_decrypt_service.py
import logging
from uuid import UUID
from cryptography.exceptions import InvalidTag

from app.db.secrets import get_secret_by_id
from app.utils.crypto import decrypt_secret, canonical_aad
from app.models.errors import SecretPersistenceError

logger = logging.getLogger(__name__)


def build_aad_from_record(record: dict) -> dict:
    aad = {
        "v": 1,
        "portal_id": record["portal_id"],
        "scope": record["scope"],
        "name": record["name"],
    }
    if record.get("action_id"):
        aad["action_id"] = record["action_id"]
    return aad


def decrypt_secret_for_test(secret_id: UUID) -> dict:
    try:
        record = get_secret_by_id(secret_id)

        aad = build_aad_from_record(record)

        value = decrypt_secret(
            ciphertext_b64=record["ciphertext"],
            nonce_b64=record["nonce"],
            dek_wrapped_b64=record["dek_wrapped"],
            dek_nonce_b64=record["dek_nonce"],
            portal_id=record["portal_id"],
            aad=aad,
        )

        return {
            "id": record["id"],
            "scope": record["scope"],
            "portal_id": record["portal_id"],
            "action_id": record.get("action_id"),
            "name": record["name"],
            "value": value,
            "kek_key_id": record["kek_key_id"],
            "created_at": record["created_at"],
            "created_by": record.get("created_by"),
        }

    except KeyError:
        raise SecretPersistenceError("Secret not found")

    except InvalidTag:
        # precise message without leaking anything
        logger.error(
            "Test decryption failed: InvalidTag",
            extra={
                "secret_id": str(secret_id),
                "portal_id": str(record.get("portal_id")) if "record" in locals() else None,
                "scope": record.get("scope") if "record" in locals() else None,
                "name": record.get("name") if "record" in locals() else None,
            },
        )
        raise SecretPersistenceError("Failed to decrypt secret (InvalidTag)")

    except Exception:
        logger.exception(
            "Test decryption failed",
            extra={"secret_id": str(secret_id)},
        )
        raise SecretPersistenceError("Failed to decrypt secret")
