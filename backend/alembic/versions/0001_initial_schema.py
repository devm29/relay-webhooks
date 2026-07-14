"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-04 14:44:00.205782
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orgs")),
    )
    op.create_table(
        "apps",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_apps_org_id_orgs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_apps")),
        sa.UniqueConstraint("org_id", "name", name=op.f("uq_apps_org_id")),
    )
    op.create_index(op.f("ix_apps_org_id"), "apps", ["org_id"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'developer', 'viewer')", name=op.f("ck_users_role")
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_users_org_id_orgs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_org_id"), "users", ["org_id"], unique=False)
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("org_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("prefix", sa.String(length=32), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("created_by", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_api_keys_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name=op.f("fk_api_keys_org_id_orgs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_api_keys_key_hash")),
    )
    op.create_index(op.f("ix_api_keys_org_id"), "api_keys", ["org_id"], unique=False)
    op.create_table(
        "endpoints",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("app_id", sa.String(length=40), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "event_types",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("rate_limit_per_second", sa.Float(), nullable=True),
        sa.Column("timeout_seconds", sa.Float(), nullable=True),
        sa.Column(
            "headers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("disabled_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["app_id"], ["apps.id"], name=op.f("fk_endpoints_app_id_apps"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_endpoints")),
    )
    op.create_index(op.f("ix_endpoints_app_id"), "endpoints", ["app_id"], unique=False)
    op.create_table(
        "event_types",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("app_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("payload_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["app_id"], ["apps.id"], name=op.f("fk_event_types_app_id_apps"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_types")),
        sa.UniqueConstraint("app_id", "name", name=op.f("uq_event_types_app_id")),
    )
    op.create_index(op.f("ix_event_types_app_id"), "event_types", ["app_id"], unique=False)
    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("app_id", sa.String(length=40), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["app_id"], ["apps.id"], name=op.f("fk_messages_app_id_apps"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index("ix_messages_app_created", "messages", ["app_id", "id"], unique=False)
    op.create_index(
        "uq_messages_app_idempotency",
        "messages",
        ["app_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_table(
        "breaker_state",
        sa.Column("endpoint_id", sa.String(length=40), nullable=False),
        sa.Column(
            "state", sa.String(length=16), server_default=sa.text("'closed'"), nullable=False
        ),
        sa.Column(
            "consecutive_failures", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("trip_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("probe_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('closed', 'open', 'half_open')", name=op.f("ck_breaker_state_state")
        ),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["endpoints.id"],
            name=op.f("fk_breaker_state_endpoint_id_endpoints"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("endpoint_id", name=op.f("pk_breaker_state")),
    )
    op.create_table(
        "deliveries",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("app_id", sa.String(length=40), nullable=False),
        sa.Column("message_id", sa.String(length=40), nullable=False),
        sa.Column("endpoint_id", sa.String(length=40), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("schedule_index", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(length=40), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("replay_pending", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'dead')", name=op.f("ck_deliveries_status")
        ),
        sa.ForeignKeyConstraint(
            ["app_id"], ["apps.id"], name=op.f("fk_deliveries_app_id_apps"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["endpoints.id"],
            name=op.f("fk_deliveries_endpoint_id_endpoints"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_deliveries_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deliveries")),
        sa.UniqueConstraint("message_id", "endpoint_id", name=op.f("uq_deliveries_message_id")),
    )
    op.create_index("ix_deliveries_app_id", "deliveries", ["app_id", "id"], unique=False)
    op.create_index(
        "ix_deliveries_due",
        "deliveries",
        ["next_attempt_at"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_deliveries_endpoint_status", "deliveries", ["endpoint_id", "status"], unique=False
    )
    op.create_table(
        "endpoint_secrets",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("endpoint_id", sa.String(length=40), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["endpoints.id"],
            name=op.f("fk_endpoint_secrets_endpoint_id_endpoints"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_endpoint_secrets")),
    )
    op.create_index(
        op.f("ix_endpoint_secrets_endpoint_id"), "endpoint_secrets", ["endpoint_id"], unique=False
    )
    op.create_table(
        "attempts",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("app_id", sa.String(length=40), nullable=False),
        sa.Column("delivery_id", sa.String(length=40), nullable=False),
        sa.Column("message_id", sa.String(length=40), nullable=False),
        sa.Column("endpoint_id", sa.String(length=40), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("response_snippet", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["app_id"], ["apps.id"], name=op.f("fk_attempts_app_id_apps"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["deliveries.id"],
            name=op.f("fk_attempts_delivery_id_deliveries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["endpoints.id"],
            name=op.f("fk_attempts_endpoint_id_endpoints"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_attempts_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attempts")),
    )
    op.create_index("ix_attempts_app_id", "attempts", ["app_id", "id"], unique=False)
    op.create_index("ix_attempts_delivery", "attempts", ["delivery_id"], unique=False)
    op.create_index(
        "ix_attempts_endpoint_started", "attempts", ["endpoint_id", "started_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_attempts_endpoint_started", table_name="attempts")
    op.drop_index("ix_attempts_delivery", table_name="attempts")
    op.drop_index("ix_attempts_app_id", table_name="attempts")
    op.drop_table("attempts")
    op.drop_index(op.f("ix_endpoint_secrets_endpoint_id"), table_name="endpoint_secrets")
    op.drop_table("endpoint_secrets")
    op.drop_index("ix_deliveries_endpoint_status", table_name="deliveries")
    op.drop_index(
        "ix_deliveries_due", table_name="deliveries", postgresql_where=sa.text("status = 'pending'")
    )
    op.drop_index("ix_deliveries_app_id", table_name="deliveries")
    op.drop_table("deliveries")
    op.drop_table("breaker_state")
    op.drop_index(
        "uq_messages_app_idempotency",
        table_name="messages",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_index("ix_messages_app_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_event_types_app_id"), table_name="event_types")
    op.drop_table("event_types")
    op.drop_index(op.f("ix_endpoints_app_id"), table_name="endpoints")
    op.drop_table("endpoints")
    op.drop_index(op.f("ix_api_keys_org_id"), table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index(op.f("ix_users_org_id"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_apps_org_id"), table_name="apps")
    op.drop_table("apps")
    op.drop_table("orgs")
