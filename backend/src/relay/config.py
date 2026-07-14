from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from relay.domain.models import MAX_ENDPOINT_TIMEOUT_SECONDS

DEV_JWT_SECRET = "dev-only-jwt-secret-change-me-0123456789"  # noqa: S105
DEV_API_KEY_PEPPER = "dev-only-api-key-pepper-change-me"
MIN_SECRET_BYTES = 32
LEASE_SAFETY_MARGIN_SECONDS = 15.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RELAY_",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = False

    database_url: str = "postgresql+asyncpg://relay@127.0.0.1:5508/relay"
    db_pool_size: int = 10

    api_host: str = "127.0.0.1"
    api_port: int = 8108
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3108"])

    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    jwt_ttl_minutes: int = 720
    api_key_pepper: SecretStr = SecretStr(DEV_API_KEY_PEPPER)

    login_attempts_per_minute: float = Field(default=10.0, gt=0)
    login_attempts_per_minute_per_client: float = Field(default=60.0, gt=0)

    dispatcher_workers: int = 16
    dispatcher_lease_seconds: int = 60
    dispatcher_idle_poll_seconds: float = 1.0
    delivery_timeout_seconds: float = Field(default=15.0, gt=0, le=MAX_ENDPOINT_TIMEOUT_SECONDS)
    response_snippet_bytes: int = 2048

    retry_base_seconds: float = 5.0
    retry_max_backoff_seconds: float = 3600.0
    retry_max_attempts: int = 8
    retry_after_cap_seconds: float = 3600.0

    breaker_failure_threshold: int = 5
    breaker_base_cooldown_seconds: float = 30.0
    breaker_max_cooldown_seconds: float = 900.0
    breaker_disable_after_trips: int = 8
    breaker_probe_timeout_seconds: float = 60.0

    secret_rotation_overlap_seconds: int = 86_400
    # Unset means: allowed in development and test, refused in production.
    allow_private_endpoints: bool | None = None

    chaos_mount: bool = False
    chaos_verify_secret: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def asyncpg_dsn(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    @property
    def private_endpoints_allowed(self) -> bool:
        if self.allow_private_endpoints is None:
            return self.env != "production"
        return self.allow_private_endpoints

    @model_validator(mode="after")
    def _check(self) -> Self:
        # The lease has to outlive the slowest request any endpoint is allowed to make.
        floor = MAX_ENDPOINT_TIMEOUT_SECONDS + LEASE_SAFETY_MARGIN_SECONDS
        if self.dispatcher_lease_seconds < floor:
            raise ValueError(
                f"dispatcher_lease_seconds must be at least {floor:g} so a lease outlives "
                "the slowest permitted webhook request"
            )
        if self.env != "production":
            return self
        for name, secret, default in (
            ("jwt_secret", self.jwt_secret, DEV_JWT_SECRET),
            ("api_key_pepper", self.api_key_pepper, DEV_API_KEY_PEPPER),
        ):
            value = secret.get_secret_value()
            if value == default or len(value.encode()) < MIN_SECRET_BYTES:
                raise ValueError(
                    f"RELAY_{name.upper()} must be set to a random value of at least "
                    f"{MIN_SECRET_BYTES} bytes in production"
                )
        if self.chaos_mount:
            raise ValueError("RELAY_CHAOS_MOUNT exposes unauthenticated routes; not in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
