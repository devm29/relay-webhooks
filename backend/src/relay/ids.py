"""Prefixed, time-sortable identifiers (ULID layout: 48-bit ms timestamp + 80 random bits)."""

import secrets
import time

_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        chars.append(_ALPHABET[rem])
    return "".join(reversed(chars))


def new_id(prefix: str, *, now_ms: int | None = None) -> str:
    ts = now_ms if now_ms is not None else time.time_ns() // 1_000_000
    raw = (ts << 80) | secrets.randbits(80)
    return f"{prefix}_{_encode(raw, 26)}"
