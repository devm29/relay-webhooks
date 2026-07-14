from datetime import datetime, timedelta

import jwt
from pydantic import BaseModel, ValidationError

from relay.domain.enums import Role
from relay.domain.errors import AuthenticationError

_ALGORITHM = "HS256"
_AUDIENCE = "relay-console"


class SessionClaims(BaseModel):
    sub: str
    org: str
    role: Role
    exp: int
    iat: int


def issue_session_token(
    *, user_id: str, org_id: str, role: Role, secret: str, ttl: timedelta, now: datetime
) -> tuple[str, datetime]:
    expires_at = now + ttl
    payload = {
        "sub": user_id,
        "org": org_id,
        "role": role.value,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "aud": _AUDIENCE,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM), expires_at


def decode_session_token(token: str, secret: str, now: datetime) -> SessionClaims:
    # Expiry is checked against the injected clock rather than PyJWT's wall clock.
    try:
        raw = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            audience=_AUDIENCE,
            options={"verify_exp": False, "require": ["exp", "iat", "sub"]},
        )
        claims = SessionClaims.model_validate(raw)
    except (jwt.PyJWTError, ValidationError) as exc:
        raise AuthenticationError("invalid session token") from exc
    if claims.exp <= int(now.timestamp()):
        raise AuthenticationError("session expired, sign in again")
    return claims
