"""Postgres as a delivery queue.

Workers claim due rows with ``FOR UPDATE SKIP LOCKED`` and stamp them with a lease
token and expiry. A worker that crashes simply lets its lease lapse, after which the
row is claimable again. Every write back is fenced on the lease token, so a worker
whose lease was reclaimed cannot overwrite the newer owner's result.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import CursorResult, and_, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from relay.domain.enums import DeliveryStatus
from relay.domain.pacing import Pace, take
from relay.ids import new_id
from relay.persistence.repositories.catalog import ensure_breaker_row
from relay.persistence.tables import BreakerStateRow, Delivery, Endpoint


@dataclass(frozen=True, slots=True)
class DeliveryJob:
    delivery_id: str
    lease_token: str
    app_id: str
    message_id: str
    endpoint_id: str
    attempt_count: int
    schedule_index: int
    replay: bool
    event_type: str
    payload: dict[str, Any]
    message_created_at: datetime
    endpoint_url: str
    timeout_seconds: float | None
    rate_limit_per_second: float | None
    headers: dict[str, str]


_CANDIDATES_SQL = text(
    """
    SELECT d.id, d.endpoint_id, e.rate_limit_per_second AS rate
    FROM deliveries d
    JOIN endpoints e ON e.id = d.endpoint_id
    LEFT JOIN breaker_state b ON b.endpoint_id = d.endpoint_id
    WHERE d.status = 'pending'
      AND d.next_attempt_at <= :now
      AND (d.lease_until IS NULL OR d.lease_until <= :now)
      AND NOT e.disabled
      AND e.deleted_at IS NULL
      AND (b.state = 'open' AND b.open_until > :now) IS NOT TRUE
      AND (b.state = 'half_open' AND b.probe_started_at > :probe_cutoff) IS NOT TRUE
      AND (
        e.rate_limit_per_second IS NULL
        OR b.rate_tat IS NULL
        OR b.rate_tat <= :now + make_interval(
             secs => (GREATEST(e.rate_limit_per_second, 1) - 1) / e.rate_limit_per_second)
      )
    ORDER BY d.next_attempt_at
    LIMIT :limit
    FOR UPDATE OF d SKIP LOCKED
    """
)

_LEASE_SQL = text(
    """
    UPDATE deliveries d
    SET lease_until = :lease_until, lease_token = :token, updated_at = :now
    FROM messages m, endpoints e
    WHERE d.id = ANY(:ids) AND m.id = d.message_id AND e.id = d.endpoint_id
    RETURNING d.id, d.app_id, d.message_id, d.endpoint_id, d.attempt_count, d.schedule_index,
              d.replay_pending, m.event_type, m.payload, m.created_at AS message_created_at,
              e.url, e.timeout_seconds, e.rate_limit_per_second, e.headers
    """
)


async def lease_due(
    session: AsyncSession,
    *,
    now: datetime,
    lease_for: timedelta,
    limit: int,
    probe_timeout: timedelta = timedelta(seconds=60),
) -> list[DeliveryJob]:
    """Claim up to ``limit`` due deliveries.

    Rate limits are enforced here rather than after the lease: endpoints whose pace does
    not allow another request yet are filtered out of the candidate query, and the slots
    for the rest are taken in the same transaction. A backlog for a slow endpoint therefore
    never occupies workers or churns rows while healthy endpoints wait.
    """
    candidates = (
        await session.execute(
            _CANDIDATES_SQL,
            {"now": now, "limit": limit, "probe_cutoff": now - probe_timeout},
        )
    ).all()
    if not candidates:
        return []

    chosen: list[str] = []
    paced: dict[str, list[str]] = defaultdict(list)
    rates: dict[str, float] = {}
    for row in candidates:
        if row.rate is None:
            chosen.append(row.id)
        else:
            paced[row.endpoint_id].append(row.id)
            rates[row.endpoint_id] = row.rate
    # Sorted so concurrent leasers take breaker rows in the same order.
    for endpoint_id in sorted(paced):
        ids = paced[endpoint_id]
        admitted = await take_slots(session, endpoint_id, Pace(rates[endpoint_id]), len(ids), now)
        chosen.extend(ids[:admitted])
    if not chosen:
        return []

    token = new_id("lse")
    result = await session.execute(
        _LEASE_SQL,
        {"ids": chosen, "lease_until": now + lease_for, "token": token, "now": now},
    )
    return [
        DeliveryJob(
            delivery_id=row.id,
            lease_token=token,
            app_id=row.app_id,
            message_id=row.message_id,
            endpoint_id=row.endpoint_id,
            attempt_count=row.attempt_count,
            schedule_index=row.schedule_index,
            replay=row.replay_pending,
            event_type=row.event_type,
            payload=row.payload,
            message_created_at=row.message_created_at,
            endpoint_url=row.url,
            timeout_seconds=row.timeout_seconds,
            rate_limit_per_second=row.rate_limit_per_second,
            headers=row.headers or {},
        )
        for row in result
    ]


async def take_slots(
    session: AsyncSession, endpoint_id: str, pace: Pace, wanted: int, now: datetime
) -> int:
    await ensure_breaker_row(session, endpoint_id)
    tat = await session.scalar(
        select(BreakerStateRow.rate_tat)
        .where(BreakerStateRow.endpoint_id == endpoint_id)
        .with_for_update()
    )
    grant = take(pace, tat, now, wanted)
    if grant.admitted:
        await session.execute(
            update(BreakerStateRow)
            .where(BreakerStateRow.endpoint_id == endpoint_id)
            .values(rate_tat=grant.tat)
            .execution_options(synchronize_session=False)
        )
    return grant.admitted


def _fenced(job: DeliveryJob) -> Any:
    return and_(Delivery.id == job.delivery_id, Delivery.lease_token == job.lease_token)


async def _apply(session: AsyncSession, job: DeliveryJob, **values: Any) -> bool:
    result = await session.execute(
        update(Delivery)
        .where(_fenced(job))
        .values(lease_until=None, lease_token=None, **values)
        .execution_options(synchronize_session=False)
    )
    assert isinstance(result, CursorResult)
    return result.rowcount == 1


async def release(
    session: AsyncSession, job: DeliveryJob, *, retry_at: datetime, now: datetime
) -> bool:
    """Hand a leased delivery back without counting an attempt (breaker open)."""
    return await _apply(session, job, next_attempt_at=retry_at, updated_at=now)


async def mark_succeeded(
    session: AsyncSession, job: DeliveryJob, *, status_code: int, now: datetime
) -> bool:
    return await _apply(
        session,
        job,
        status=DeliveryStatus.SUCCEEDED.value,
        attempt_count=Delivery.attempt_count + 1,
        schedule_index=Delivery.schedule_index + 1,
        last_status_code=status_code,
        last_error=None,
        next_attempt_at=None,
        replay_pending=False,
        delivered_at=now,
        updated_at=now,
    )


async def mark_failed(
    session: AsyncSession,
    job: DeliveryJob,
    *,
    status_code: int | None,
    error: str | None,
    next_attempt_at: datetime | None,
    now: datetime,
) -> bool:
    status = DeliveryStatus.DEAD if next_attempt_at is None else DeliveryStatus.PENDING
    return await _apply(
        session,
        job,
        status=status.value,
        attempt_count=Delivery.attempt_count + 1,
        schedule_index=Delivery.schedule_index + 1,
        last_status_code=status_code,
        last_error=error,
        next_attempt_at=next_attempt_at,
        replay_pending=False,
        updated_at=now,
    )


def _replayable(now: datetime) -> Any:
    not_in_flight = or_(
        Delivery.status != DeliveryStatus.PENDING.value,
        Delivery.lease_until.is_(None),
        Delivery.lease_until <= now,
    )
    endpoint_live = Delivery.endpoint_id.in_(
        select(Endpoint.id).where(Endpoint.app_id == Delivery.app_id, Endpoint.deleted_at.is_(None))
    )
    return and_(not_in_flight, endpoint_live)


def _replay_values(now: datetime) -> dict[str, Any]:
    return {
        "status": DeliveryStatus.PENDING.value,
        "next_attempt_at": now,
        "schedule_index": 0,
        "replay_pending": True,
        "lease_until": None,
        "lease_token": None,
        "updated_at": now,
    }


async def replay_one(session: AsyncSession, app_id: str, delivery_id: str, now: datetime) -> bool:
    result = await session.execute(
        update(Delivery)
        .where(Delivery.id == delivery_id, Delivery.app_id == app_id, _replayable(now))
        .values(**_replay_values(now))
        .execution_options(synchronize_session=False)
    )
    assert isinstance(result, CursorResult)
    return result.rowcount == 1


async def replay_many(
    session: AsyncSession,
    app_id: str,
    *,
    status: DeliveryStatus,
    endpoint_id: str | None,
    since: datetime | None,
    until: datetime | None,
    now: datetime,
) -> int:
    conditions = [Delivery.app_id == app_id, Delivery.status == status.value, _replayable(now)]
    if endpoint_id is not None:
        conditions.append(Delivery.endpoint_id == endpoint_id)
    if since is not None:
        conditions.append(Delivery.created_at >= since)
    if until is not None:
        conditions.append(Delivery.created_at < until)
    result = await session.execute(
        update(Delivery)
        .where(*conditions)
        .values(**_replay_values(now))
        .execution_options(synchronize_session=False)
    )
    assert isinstance(result, CursorResult)
    return result.rowcount


async def bury_endpoint(session: AsyncSession, endpoint_id: str, now: datetime) -> int:
    """Dead-letter whatever was still queued for an endpoint that is being deleted."""
    result = await session.execute(
        update(Delivery)
        .where(
            Delivery.endpoint_id == endpoint_id,
            Delivery.status == DeliveryStatus.PENDING.value,
        )
        .values(
            status=DeliveryStatus.DEAD.value,
            next_attempt_at=None,
            lease_until=None,
            lease_token=None,
            last_error="endpoint deleted",
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    assert isinstance(result, CursorResult)
    return result.rowcount


async def resume_endpoint(session: AsyncSession, endpoint_id: str, now: datetime) -> None:
    """Bring parked deliveries forward once an endpoint is re-enabled or its breaker reset."""
    await session.execute(
        update(Delivery)
        .where(
            Delivery.endpoint_id == endpoint_id,
            Delivery.status == DeliveryStatus.PENDING.value,
            or_(Delivery.lease_until.is_(None), Delivery.lease_until <= now),
            Delivery.next_attempt_at > now,
        )
        .values(next_attempt_at=now, updated_at=now)
        .execution_options(synchronize_session=False)
    )
