"""API keys are 192-bit random tokens, so a peppered SHA-256 is enough at rest and
keeps the per-request lookup to a single indexed equality match. Passwords, which are
low-entropy, use argon2 instead."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

KEY_PREFIX = "rk_"
_DISPLAY_PREFIX_LEN = 10


@dataclass(frozen=True, slots=True)
class GeneratedKey:
    plaintext: str
    prefix: str
    key_hash: str


def hash_api_key(key: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), key.encode(), hashlib.sha256).hexdigest()


def generate_api_key(pepper: str) -> GeneratedKey:
    plaintext = KEY_PREFIX + secrets.token_urlsafe(24)
    return GeneratedKey(
        plaintext=plaintext,
        prefix=plaintext[:_DISPLAY_PREFIX_LEN],
        key_hash=hash_api_key(plaintext, pepper),
    )


def looks_like_api_key(token: str) -> bool:
    return token.startswith(KEY_PREFIX)
