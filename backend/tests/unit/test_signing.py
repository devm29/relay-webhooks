from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from relay.signing import (
    Webhook,
    WebhookVerificationError,
    generate_secret,
    sign,
    signature_headers,
)

# Reference vector published with the Standard Webhooks / Svix documentation.
SPEC_SECRET = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
SPEC_MSG_ID = "msg_p5jXN8AQM9LWM0D4loKWxJek"
SPEC_TIMESTAMP = 1614265330
SPEC_BODY = b'{"test": 2432232314}'
SPEC_SIGNATURE = "v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE="

AT = datetime.fromtimestamp(SPEC_TIMESTAMP, UTC)

Mutation = Callable[[dict[str, str], bytes], tuple[dict[str, str], bytes]]


def test_matches_published_reference_signature() -> None:
    assert sign(SPEC_SECRET, SPEC_MSG_ID, SPEC_TIMESTAMP, SPEC_BODY) == SPEC_SIGNATURE


def test_round_trip_and_header_case_insensitivity() -> None:
    secret = generate_secret()
    headers = signature_headers([secret], "msg_1", SPEC_TIMESTAMP, b"{}")
    upper = {k.upper(): v for k, v in headers.items()}
    Webhook(secret).verify(b"{}", upper, now=AT)


def test_rotation_window_signs_with_every_active_secret() -> None:
    old, new = generate_secret(), generate_secret()
    headers = signature_headers([new, old], "msg_1", SPEC_TIMESTAMP, b"{}")
    assert len(headers["webhook-signature"].split(" ")) == 2
    Webhook(old).verify(b"{}", headers, now=AT)
    Webhook(new).verify(b"{}", headers, now=AT)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda h, b: (h | {"webhook-id": "msg_other"}, b),
        lambda h, b: (h, b + b" "),
        lambda h, b: (h | {"webhook-signature": "v2," + h["webhook-signature"][3:]}, b),
        lambda h, b: ({k: v for k, v in h.items() if k != "webhook-signature"}, b),
    ],
    ids=["id-swapped", "body-tampered", "unknown-version", "missing-header"],
)
def test_rejects_tampering(mutate: Mutation) -> None:
    headers = signature_headers([SPEC_SECRET], SPEC_MSG_ID, SPEC_TIMESTAMP, SPEC_BODY)
    bad_headers, bad_body = mutate(headers, SPEC_BODY)
    with pytest.raises(WebhookVerificationError):
        Webhook(SPEC_SECRET).verify(bad_body, bad_headers, now=AT)


def test_rejects_wrong_secret_and_stale_timestamps() -> None:
    headers = signature_headers([SPEC_SECRET], SPEC_MSG_ID, SPEC_TIMESTAMP, SPEC_BODY)
    with pytest.raises(WebhookVerificationError):
        Webhook(generate_secret()).verify(SPEC_BODY, headers, now=AT)
    with pytest.raises(WebhookVerificationError, match="too old"):
        Webhook(SPEC_SECRET).verify(SPEC_BODY, headers, now=AT + timedelta(minutes=6))
    with pytest.raises(WebhookVerificationError, match="too new"):
        Webhook(SPEC_SECRET).verify(SPEC_BODY, headers, now=AT - timedelta(minutes=6))
