"""
Cryptographic Utilities for Novocode Runtime

This module provides AES-GCM encryption and decryption functionality with a
key-wrapping pattern for secure secret storage. It implements industry-standard
cryptographic practices for confidentiality, integrity, and authenticity.

Security Architecture:
- AES-256-GCM for authenticated encryption (confidentiality + integrity)
- Key Encryption Key (KEK) wraps Data Encryption Keys (DEK)
- Additional Authenticated Data (AAD) for context binding
- Per-secret unique DEKs for key isolation and forward secrecy
- Cryptographically secure random nonce generation

Key Management:
- KEK derived from environment variable (KEK_HEX)
- Unique DEK generated per secret for key isolation
- DEKs are wrapped using KEK and stored with encrypted data
- Support for KEK rotation through key_id tracking

Threat Mitigation:
- Authentication tags prevent ciphertext tampering
- AAD prevents ciphertext replay across contexts
- Unique nonces prevent nonce reuse attacks
- Key isolation limits impact of key compromise

Environment Variables:
- KEK_HEX: Hex-encoded Key Encryption Key (32 bytes for AES-256)
"""

import os
import json
import secrets
import re
import base64
import logging
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

logger = logging.getLogger(__name__)

# Load Key Encryption Key (KEK) from environment
try:
    KEK = bytes.fromhex(os.environ["KEK_HEX"])
except KeyError as exc:
    raise RuntimeError("KEK_HEX environment variable is not set") from exc
except ValueError as exc:
    raise RuntimeError("KEK_HEX is not valid hex") from exc

# Regex for validating hex strings
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


# -------------------------
# Additional Authenticated Data (AAD) Handling
# -------------------------

def canonical_aad(aad: dict) -> bytes:
    """
    Create deterministic canonical serialization of AAD for AES-GCM.

    This function converts AAD dictionary into a canonical JSON representation
    to ensure consistent serialization across encryption and decryption operations.
    Any change in ordering or formatting WILL break decryption of existing data.

    Canonical Format:
    - JSON with sorted keys (deterministic ordering)
    - Compact separators (no whitespace)
    - UTF-8 encoding

    Args:
        aad: Dictionary containing Additional Authenticated Data

    Returns:
        bytes: Canonical JSON representation of AAD

    Raises:
        TypeError: If AAD is not a dictionary
    """
    if not isinstance(aad, dict):
        raise TypeError("AAD must be a dict")

    # Use deterministic JSON serialization
    return json.dumps(
        aad,
        sort_keys=True,        # Sort keys for consistent ordering
        separators=(",", ":"),  # Compact format without whitespace
    ).encode("utf-8")


# -------------------------
# Encryption
# -------------------------

def encrypt_secret(
    *,
    plaintext: str,
    portal_id: str,
    name: str,
    scope: str,
    action_id: str | None,
) -> dict:
    try:
        if not plaintext:
            raise ValueError("plaintext must be non-empty")
        if not portal_id:
            raise ValueError("portal_id is required")
        if not name:
            raise ValueError("name is required")

        # Generate DEK
        data_encryption_key = AESGCM.generate_key(bit_length=256)
        aesgcm = AESGCM(data_encryption_key)
        nonce = secrets.token_bytes(12)

        aad = {
            "v": 1,
            "portal_id": portal_id,
            "scope": scope,
            "name": name,
        }
        if action_id:
            aad["action_id"] = action_id

        ciphertext = aesgcm.encrypt(
            nonce,
            plaintext.encode("utf-8"),
            canonical_aad(aad),
        )

        # Wrap DEK with KEK
        kek_cipher = AESGCM(KEK)
        dek_nonce = secrets.token_bytes(12)

        dek_wrapped = kek_cipher.encrypt(
            dek_nonce,
            data_encryption_key,
            portal_id.encode("utf-8"),
        )

        return {
            "ciphertext": ciphertext,
            "nonce": nonce,
            "dek_wrapped": dek_wrapped,
            "dek_nonce": dek_nonce,
            "aad": aad,  # stored for audit/debug only
            "kek_key_id": "primary-v1",
        }

    except Exception:
        logger.exception(
            "Secret encryption failed",
            extra={
                "portal_id": portal_id,
                "scope": scope,
                "secret_name": name,
                "action_id": action_id,
            },
        )
        raise


# -------------------------
# Bytea decoding
# -------------------------

def decode_bytea(value: str) -> bytes:
    if value is None:
        raise ValueError("bytea value is None")

    if isinstance(value, (bytes, bytearray)):
        return bytes(value)

    if not isinstance(value, str):
        raise TypeError("bytea value must be str or bytes")

    s = value.strip()

    # Hex form: \x...
    if s.startswith("\\x"):
        hex_part = s[2:]
        if not _HEX_RE.match(hex_part) or (len(hex_part) % 2 != 0):
            raise ValueError("Invalid hex bytea format")
        return bytes.fromhex(hex_part)

    # Base64 (PostgREST often omits padding)
    try:
        padding = "=" * (-len(s) % 4)
        return base64.urlsafe_b64decode((s + padding).encode("ascii"))
    except Exception as exc:
        raise ValueError("Invalid base64 bytea format") from exc


# -------------------------
# Decryption
# -------------------------

def decrypt_secret(
    *,
    ciphertext_b64: str,
    nonce_b64: str,
    dek_wrapped_b64: str,
    dek_nonce_b64: str,
    portal_id: str,
    aad: dict,
) -> str:
    """
    Decrypts a secret using envelope encryption.

    MUST only be called in trusted backend contexts.
    """

    try:
        ciphertext = decode_bytea(ciphertext_b64)
        nonce = decode_bytea(nonce_b64)
        dek_wrapped = decode_bytea(dek_wrapped_b64)
        dek_nonce = decode_bytea(dek_nonce_b64)

        kek_cipher = AESGCM(KEK)

        try:
            data_encryption_key = kek_cipher.decrypt(
                dek_nonce,
                dek_wrapped,
                portal_id.encode("utf-8"),
            )
        except InvalidTag:
            logger.error(
                "Secret unwrap failed: InvalidTag (DEK unwrap)",
                extra={"portal_id": portal_id},
            )
            raise

        aesgcm = AESGCM(data_encryption_key)

        try:
            plaintext = aesgcm.decrypt(
                nonce,
                ciphertext,
                canonical_aad(aad),
            )
        except InvalidTag:
            logger.error(
                "Secret decrypt failed: InvalidTag (payload)",
                extra={"portal_id": portal_id, "aad_keys": sorted(aad.keys())},
            )
            raise

        return plaintext.decode("utf-8")

    except Exception:
        logger.exception("Secret decryption failed",
                         extra={"portal_id": portal_id})
        raise
