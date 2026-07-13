import pytest
from pydantic import SecretStr, ValidationError

from relay.config import DEV_JWT_SECRET, Settings

STRONG = SecretStr("x" * 48)


def _production(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "env": "production",
        "jwt_secret": STRONG,
        "api_key_pepper": SecretStr("y" * 48),
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_production_refuses_default_or_short_secrets() -> None:
    with pytest.raises(ValidationError, match="RELAY_JWT_SECRET"):
        _production(jwt_secret=SecretStr(DEV_JWT_SECRET))
    with pytest.raises(ValidationError, match="RELAY_API_KEY_PEPPER"):
        _production(api_key_pepper=SecretStr("short"))


def test_production_blocks_private_endpoints_and_chaos_by_default() -> None:
    settings = _production()
    assert settings.private_endpoints_allowed is False
    assert _production(allow_private_endpoints=True).private_endpoints_allowed is True
    with pytest.raises(ValidationError, match="CHAOS_MOUNT"):
        _production(chaos_mount=True)


def test_development_allows_private_endpoints() -> None:
    assert Settings(env="development").private_endpoints_allowed is True


def test_lease_must_outlive_the_slowest_request() -> None:
    with pytest.raises(ValidationError, match="dispatcher_lease_seconds"):
        Settings(dispatcher_lease_seconds=10)
