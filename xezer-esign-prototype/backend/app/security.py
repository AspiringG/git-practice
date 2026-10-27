"""PIN hashing and document fingerprinting.

PINs are stored as salted PBKDF2-HMAC-SHA256 hashes (stdlib only). A signing
PIN is never stored, logged or returned in plaintext.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import unicodedata
from typing import Any

PBKDF2_ITERATIONS = int(os.environ.get("ESIGN_PBKDF2_ITERATIONS", "210000"))


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_pin(pin: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    expected = base64.b64decode(digest_b64)
    actual = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), base64.b64decode(salt_b64), int(iterations)
    )
    return hmac.compare_digest(actual, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def _normalize(value: Any) -> Any:
    """NFC-normalise text so 'ə' or 'ü' typed differently still hash the same."""
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {_normalize(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def canonical_json(snapshot: dict) -> str:
    """Deterministic serialisation: sorted keys, no whitespace, UTF-8, NFC."""
    return json.dumps(_normalize(snapshot), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(snapshot: dict) -> str:
    return hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()
