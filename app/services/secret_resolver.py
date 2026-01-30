# services/secret_resolver.py
import logging
from uuid import UUID

from app.db.secrets import get_secret_by_id
from app.utils.crypto import decrypt_secret

logger = logging.getLogger(__name__)


def build_aad(record: dict) -> dict:
    aad = {
        "v": 1,
        "portal_id": record["portal_id"],
        "scope": record["scope"],
        "name": record["name"],
    }
    if record.get("action_id"):
        aad["action_id"] = record["action_id"]
    return aad


def resolve_secret_value(secret_id: UUID) -> str:
    record = get_secret_by_id(secret_id)

    try:
        return decrypt_secret(
            ciphertext_b64=record["ciphertext"],
            nonce_b64=record["nonce"],
            dek_wrapped_b64=record["dek_wrapped"],
            dek_nonce_b64=record["dek_nonce"],
            portal_id=record["portal_id"],
            aad=build_aad(record),
        )
    except Exception:
        logger.exception(
            "Failed to resolve secret",
            extra={
                "secret_id": str(secret_id),
                "portal_id": record.get("portal_id"),
            },
        )
        raise
