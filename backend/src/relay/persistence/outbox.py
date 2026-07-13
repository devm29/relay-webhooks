"""Transactional outbox: a message and its per-endpoint deliveries are written in the
same transaction, so a published event is never lost and never half fanned out."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from relay.ids import new_id
from relay.persistence.tables import Delivery, Endpoint, Message


@dataclass(frozen=True, slots=True)
class OutboxResult:
    message: Message
    fanout: int
    created: bool


async def write_message(
    session: AsyncSession,
    *,
    app_id: str,
    event_type: str,
    event_id: str | None,
    payload: dict[str, Any],
    idempotency_key: str | None,
    fingerprint: str,
    now: datetime,
) -> OutboxResult:
    message_id = new_id("msg")
    stmt = (
        pg_insert(Message)
        .values(
            id=message_id,
            app_id=app_id,
            event_type=event_type,
            event_id=event_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            payload=payload,
            created_at=now,
        )
        .on_conflict_do_nothing(
            index_elements=[Message.app_id, Message.idempotency_key],
            index_where=text("idempotency_key IS NOT NULL"),
        )
        .returning(Message.id)
    )
    inserted = (await session.execute(stmt)).scalar_one_or_none()
    if inserted is None:
        existing = (
            await session.execute(
                select(Message).where(
                    Message.app_id == app_id, Message.idempotency_key == idempotency_key
                )
            )
        ).scalar_one()
        fanout = await session.scalar(
            select(func.count()).select_from(Delivery).where(Delivery.message_id == existing.id)
        )
        return OutboxResult(message=existing, fanout=fanout or 0, created=False)

    endpoint_ids = (
        (
            await session.execute(
                select(Endpoint.id).where(
                    Endpoint.app_id == app_id,
                    Endpoint.disabled.is_(False),
                    Endpoint.deleted_at.is_(None),
                    or_(
                        func.cardinality(Endpoint.event_types) == 0,
                        Endpoint.event_types.any_() == event_type,
                    ),
                )
            )
        )
        .scalars()
        .all()
    )

    if endpoint_ids:
        await session.execute(
            insert(Delivery),
            [
                {
                    "id": new_id("dlv"),
                    "app_id": app_id,
                    "message_id": message_id,
                    "endpoint_id": endpoint_id,
                    "status": "pending",
                    "next_attempt_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
                for endpoint_id in endpoint_ids
            ],
        )

    message = await session.get(Message, message_id)
    assert message is not None
    return OutboxResult(message=message, fanout=len(endpoint_ids), created=True)
