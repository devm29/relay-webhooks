"""Standard Webhooks (https://www.standardwebhooks.com) signing and verification.

Signed content is ``{webhook-id}.{webhook-timestamp}.{body}``; each signature is
``v1,<base64 HMAC-SHA256>`` and multiple signatures are space-delimited, which is
what lets a receiver accept either secret during a rotation window.
"""

import base64
import hashlib
import hmac
import secrets
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

SECRET_PREFIX = "whsec_"  # noqa: S105
SIGNATURE_VERSION = "v1"
DEFAULT_TOLERANCE_SECONDS = 300


class WebhookVerificationError(Exception):
    pass


def generate_secret(num_bytes: int = 24) -> str:
    return SECRET_PREFIX + base64.b64encode(secrets.token_bytes(num_bytes)).decode()


def _secret_bytes(secret: str) -> bytes:
    raw = secret.removeprefix(SECRET_PREFIX)
    try:
        return base64.b64decode(raw, validate=True)
    except ValueError as exc:
        raise ValueError("secret must be base64, optionally prefixed with whsec_") from exc


def sign(secret: str, msg_id: str, timestamp: int, body: bytes) -> str:
    content = f"{msg_id}.{timestamp}.".encode() + body
    digest = hmac.new(_secret_bytes(secret), content, hashlib.sha256).digest()
    return f"{SIGNATURE_VERSION},{base64.b64encode(digest).decode()}"


def signature_headers(
    secrets_: Iterable[str], msg_id: str, timestamp: int, body: bytes
) -> dict[str, str]:
    signatures = " ".join(sign(secret, msg_id, timestamp, body) for secret in secrets_)
    if not signatures:
        raise ValueError("at least one signing secret is required")
    return {
        "webhook-id": msg_id,
        "webhook-timestamp": str(timestamp),
        "webhook-signature": signatures,
    }


class Webhook:
    """Receiver-side verifier. Accepts a single secret or several (e.g. old and new)."""

    def __init__(
        self, secret: str | Iterable[str], *, tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS
    ) -> None:
        candidates = [secret] if isinstance(secret, str) else list(secret)
        if not candidates:
            raise ValueError("at least one secret is required")
        self._keys = [_secret_bytes(s) for s in candidates]
        self._tolerance = tolerance_seconds

    def verify(
        self, body: bytes, headers: Mapping[str, str], *, now: datetime | None = None
    ) -> None:
        lowered = {k.lower(): v for k, v in headers.items()}
        msg_id = lowered.get("webhook-id")
        raw_ts = lowered.get("webhook-timestamp")
        raw_sigs = lowered.get("webhook-signature")
        if not msg_id or not raw_ts or not raw_sigs:
            raise WebhookVerificationError("missing required webhook headers")

        try:
            timestamp = int(raw_ts)
        except ValueError as exc:
            raise WebhookVerificationError("invalid webhook-timestamp") from exc
        current = int((now or datetime.now(UTC)).timestamp())
        if timestamp < current - self._tolerance:
            raise WebhookVerificationError("message timestamp too old")
        if timestamp > current + self._tolerance:
            raise WebhookVerificationError("message timestamp too new")

        content = f"{msg_id}.{timestamp}.".encode() + body
        expected = [
            base64.b64encode(hmac.new(key, content, hashlib.sha256).digest()) for key in self._keys
        ]
        for versioned in raw_sigs.split(" "):
            version, _, signature = versioned.partition(",")
            if version != SIGNATURE_VERSION:
                continue
            if any(hmac.compare_digest(signature.encode(), e) for e in expected):
                return
        raise WebhookVerificationError("no matching signature found")
