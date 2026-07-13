"""endpoint names, soft delete, Postgres-side rate limiting and reporting indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04 16:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("endpoints", sa.Column("name", sa.String(length=120), nullable=True))
    op.add_column("endpoints", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("breaker_state", sa.Column("rate_tat", sa.DateTime(timezone=True), nullable=True))

    op.execute("ALTER INDEX ix_messages_app_created RENAME TO ix_messages_app_id")
    op.create_index("ix_messages_app_created_at", "messages", ["app_id", "created_at"])
    op.create_index("ix_attempts_app_started", "attempts", ["app_id", "started_at"])
    op.create_index("ix_attempts_message", "attempts", ["message_id"])
    op.create_index(
        "ix_deliveries_app_unsettled",
        "deliveries",
        ["app_id", "status"],
        postgresql_where=sa.text("status <> 'succeeded'"),
    )


def downgrade() -> None:
    op.drop_index("ix_deliveries_app_unsettled", table_name="deliveries")
    op.drop_index("ix_attempts_message", table_name="attempts")
    op.drop_index("ix_attempts_app_started", table_name="attempts")
    op.drop_index("ix_messages_app_created_at", table_name="messages")
    op.execute("ALTER INDEX ix_messages_app_id RENAME TO ix_messages_app_created")

    op.drop_column("breaker_state", "rate_tat")
    op.drop_column("endpoints", "deleted_at")
    op.drop_column("endpoints", "name")
