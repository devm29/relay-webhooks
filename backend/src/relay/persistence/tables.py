from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
        list[str]: ARRAY(Text),
    }


def _created_at() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = _created_at()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'admin', 'developer', 'viewer')", name="role"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = _created_at()


class App(Base):
    __tablename__ = "apps"
    __table_args__ = (UniqueConstraint("org_id", "name"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(32))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[str]]
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime | None]
    last_used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]


class EventType(Base):
    __tablename__ = "event_types"
    __table_args__ = (UniqueConstraint("app_id", "name"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    payload_schema: Mapped[dict[str, Any] | None]
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    archived: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


class Endpoint(Base):
    __tablename__ = "endpoints"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    event_types: Mapped[list[str]] = mapped_column(server_default=text("'{}'"))
    rate_limit_per_second: Mapped[float | None] = mapped_column(Float)
    timeout_seconds: Mapped[float | None] = mapped_column(Float)
    headers: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    disabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    disabled_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()
    deleted_at: Mapped[datetime | None]


class EndpointSecret(Base):
    __tablename__ = "endpoint_secrets"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    endpoint_id: Mapped[str] = mapped_column(
        ForeignKey("endpoints.id", ondelete="CASCADE"), index=True
    )
    secret: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime | None]


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index(
            "uq_messages_app_idempotency",
            "app_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_messages_app_id", "app_id", "id"),
        Index("ix_messages_app_created_at", "app_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(160))
    event_id: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = _created_at()


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("message_id", "endpoint_id"),
        CheckConstraint("status IN ('pending', 'succeeded', 'dead')", name="status"),
        Index(
            "ix_deliveries_due",
            "next_attempt_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_deliveries_app_id", "app_id", "id"),
        Index("ix_deliveries_endpoint_status", "endpoint_id", "status"),
        Index(
            "ix_deliveries_app_unsettled",
            "app_id",
            "status",
            postgresql_where=text("status <> 'succeeded'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    endpoint_id: Mapped[str] = mapped_column(ForeignKey("endpoints.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'pending'"))
    attempt_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    schedule_index: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None]
    lease_until: Mapped[datetime | None]
    lease_token: Mapped[str | None] = mapped_column(String(40))
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    replay_pending: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    delivered_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        Index("ix_attempts_endpoint_started", "endpoint_id", "started_at"),
        Index("ix_attempts_app_id", "app_id", "id"),
        Index("ix_attempts_delivery", "delivery_id"),
        Index("ix_attempts_message", "message_id"),
        Index("ix_attempts_app_started", "app_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"))
    delivery_id: Mapped[str] = mapped_column(ForeignKey("deliveries.id", ondelete="CASCADE"))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    endpoint_id: Mapped[str] = mapped_column(ForeignKey("endpoints.id", ondelete="CASCADE"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(16))
    status_code: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    response_snippet: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime]
    next_attempt_at: Mapped[datetime | None]


class BreakerStateRow(Base):
    __tablename__ = "breaker_state"
    __table_args__ = (CheckConstraint("state IN ('closed', 'open', 'half_open')", name="state"),)

    endpoint_id: Mapped[str] = mapped_column(
        ForeignKey("endpoints.id", ondelete="CASCADE"), primary_key=True
    )
    state: Mapped[str] = mapped_column(String(16), server_default=text("'closed'"))
    consecutive_failures: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    trip_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    opened_at: Mapped[datetime | None]
    open_until: Mapped[datetime | None]
    probe_started_at: Mapped[datetime | None]
    # Theoretical arrival time of the next request under the endpoint's rate limit (GCRA).
    rate_tat: Mapped[datetime | None]
    updated_at: Mapped[datetime] = _created_at()
