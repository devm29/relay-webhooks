from datetime import UTC, datetime, timedelta

import pytest

from relay.auth.api_keys import generate_api_key, hash_api_key, looks_like_api_key
from relay.auth.passwords import hash_password, verify_password
from relay.auth.rbac import ROLE_SCOPES, can_assign_role
from relay.auth.tokens import decode_session_token, issue_session_token
from relay.domain.enums import Role, Scope
from relay.domain.errors import AuthenticationError
from relay.ids import new_id


def test_role_scopes_are_strictly_nested() -> None:
    viewer, dev, admin, owner = (
        ROLE_SCOPES[r] for r in (Role.VIEWER, Role.DEVELOPER, Role.ADMIN, Role.OWNER)
    )
    assert viewer < dev < admin <= owner
    assert Scope.MESSAGES_WRITE not in viewer
    assert Scope.API_KEYS_MANAGE not in dev


def test_admins_cannot_mint_peers_or_owners() -> None:
    assert can_assign_role(Role.ADMIN, Role.DEVELOPER)
    assert not can_assign_role(Role.ADMIN, Role.ADMIN)
    assert can_assign_role(Role.OWNER, Role.OWNER)


def test_api_keys_hash_deterministically_with_pepper() -> None:
    key = generate_api_key("pepper")
    assert looks_like_api_key(key.plaintext)
    assert key.key_hash == hash_api_key(key.plaintext, "pepper")
    assert key.key_hash != hash_api_key(key.plaintext, "other-pepper")
    assert key.plaintext.startswith(key.prefix)


def test_passwords_round_trip() -> None:
    hashed = hash_password("correct horse battery")
    assert verify_password(hashed, "correct horse battery")
    assert not verify_password(hashed, "wrong")
    assert not verify_password("not-a-hash", "anything")


def test_session_tokens_expire_and_reject_other_secrets() -> None:
    now = datetime.now(UTC)
    token, _ = issue_session_token(
        user_id="usr_1",
        org_id="org_1",
        role=Role.ADMIN,
        secret="s" * 32,
        ttl=timedelta(minutes=5),
        now=now,
    )
    assert decode_session_token(token, "s" * 32, now).role is Role.ADMIN
    with pytest.raises(AuthenticationError):
        decode_session_token(token, "t" * 32, now)
    expired, _ = issue_session_token(
        user_id="usr_1",
        org_id="org_1",
        role=Role.ADMIN,
        secret="s" * 32,
        ttl=timedelta(minutes=5),
        now=now - timedelta(hours=1),
    )
    with pytest.raises(AuthenticationError):
        decode_session_token(expired, "s" * 32, now)


def test_ids_sort_by_creation_time() -> None:
    first = new_id("msg", now_ms=1_700_000_000_000)
    second = new_id("msg", now_ms=1_700_000_000_001)
    assert first.startswith("msg_") and len(first) == 30
    assert first < second
