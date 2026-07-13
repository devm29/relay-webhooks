from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Integer, Row, Select, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from relay.domain.enums import AttemptOutcome, DeliveryStatus
from relay.persistence.repositories.base import paginate_desc, split_page
from relay.persistence.tables import Attempt, BreakerStateRow, Delivery, Endpoint, Message


@dataclass(frozen=True, slots=True)
class DeliveryView:
    delivery: Delivery
    event_type: str
    endpoint_url: str

    @property
    def id(self) -> str:
        return self.delivery.id


@dataclass(frozen=True, slots=True)
class AttemptView:
    attempt: Attempt
    event_type: str
    endpoint_url: str
    delivery_status: str

    @property
    def id(self) -> str:
        return self.attempt.id


@dataclass(frozen=True, slots=True)
class EndpointHealthRow:
    total: int
    disabled: int
    open: int
    degraded: int


@dataclass(frozen=True, slots=True)
class LatencySummary:
    total: int
    succeeded: int
    p50_ms: float | None
    p95_ms: float | None


@dataclass(frozen=True, slots=True)
class BucketRow:
    ts: datetime
    total: int
    succeeded: int
    p50_ms: float | None
    p95_ms: float | None


def _delivery_select() -> Select[Delivery, str, str]:
    return (
        select(Delivery, Message.event_type, Endpoint.url)
        .join(Message, Message.id == Delivery.message_id)
        .join(Endpoint, Endpoint.id == Delivery.endpoint_id)
    )


def _to_delivery_view(row: Row[Delivery, str, str]) -> DeliveryView:
    delivery, event_type, url = row
    return DeliveryView(delivery=delivery, event_type=event_type, endpoint_url=url)


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, app_id: str, message_id: str) -> Message | None:
        stmt = select(Message).where(Message.app_id == app_id, Message.id == message_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_page(
        self, app_id: str, *, event_type: str | None, before: str | None, limit: int
    ) -> tuple[list[Message], str | None]:
        stmt = select(Message).where(Message.app_id == app_id)
        if event_type:
            stmt = stmt.where(Message.event_type == event_type)
        rows = list(
            (
                await self.session.execute(
                    paginate_desc(stmt, Message.id, before=before, limit=limit)
                )
            ).scalars()
        )
        return split_page(rows, limit)

    async def count_since(self, app_id: str, since: datetime) -> int:
        stmt = select(func.count()).where(Message.app_id == app_id, Message.created_at >= since)
        return int(await self.session.scalar(stmt) or 0)


class DeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, app_id: str, delivery_id: str) -> DeliveryView | None:
        stmt = _delivery_select().where(Delivery.app_id == app_id, Delivery.id == delivery_id)
        row = (await self.session.execute(stmt)).one_or_none()
        return _to_delivery_view(row) if row else None

    async def for_message(self, message_id: str) -> list[DeliveryView]:
        stmt = _delivery_select().where(Delivery.message_id == message_id).order_by(Delivery.id)
        return [_to_delivery_view(row) for row in await self.session.execute(stmt)]

    async def list_page(
        self,
        app_id: str,
        *,
        status: DeliveryStatus | None,
        endpoint_id: str | None,
        before: str | None,
        limit: int,
    ) -> tuple[list[DeliveryView], str | None]:
        stmt = _delivery_select().where(Delivery.app_id == app_id)
        if status is not None:
            stmt = stmt.where(Delivery.status == status.value)
        if endpoint_id is not None:
            stmt = stmt.where(Delivery.endpoint_id == endpoint_id)
        stmt = paginate_desc(stmt, Delivery.id, before=before, limit=limit)
        views = [_to_delivery_view(row) for row in await self.session.execute(stmt)]
        return split_page(views, limit)

    async def unsettled_counts(self, app_id: str) -> dict[str, int]:
        """Pending and dead counts; served from a partial index that skips succeeded rows."""
        stmt = (
            select(Delivery.status, func.count())
            .where(Delivery.app_id == app_id, Delivery.status != DeliveryStatus.SUCCEEDED.value)
            .group_by(Delivery.status)
        )
        return {status: count for status, count in await self.session.execute(stmt)}


class AttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, attempt: Attempt) -> None:
        self.session.add(attempt)
        await self.session.flush()

    async def for_delivery(self, delivery_id: str) -> list[Attempt]:
        stmt = select(Attempt).where(Attempt.delivery_id == delivery_id).order_by(Attempt.id)
        return list((await self.session.execute(stmt)).scalars())

    async def log(
        self, app_id: str, *, endpoint_id: str | None, before: str | None, limit: int
    ) -> tuple[list[AttemptView], str | None]:
        stmt = (
            select(Attempt, Message.event_type, Endpoint.url, Delivery.status)
            .join(Message, Message.id == Attempt.message_id)
            .join(Endpoint, Endpoint.id == Attempt.endpoint_id)
            .join(Delivery, Delivery.id == Attempt.delivery_id)
            .where(Attempt.app_id == app_id)
        )
        if endpoint_id is not None:
            stmt = stmt.where(Attempt.endpoint_id == endpoint_id)
        stmt = paginate_desc(stmt, Attempt.id, before=before, limit=limit)
        views = [
            AttemptView(attempt=a, event_type=et, endpoint_url=url, delivery_status=status)
            for a, et, url, status in await self.session.execute(stmt)
        ]
        return split_page(views, limit)

    async def summary(
        self, app_id: str, *, endpoint_id: str | None, since: datetime
    ) -> LatencySummary:
        stmt = select(
            func.count(),
            func.count().filter(Attempt.outcome == AttemptOutcome.SUCCEEDED.value),
            func.percentile_cont(0.5).within_group(Attempt.latency_ms),
            func.percentile_cont(0.95).within_group(Attempt.latency_ms),
        ).where(Attempt.app_id == app_id, Attempt.started_at >= since)
        if endpoint_id is not None:
            stmt = stmt.where(Attempt.endpoint_id == endpoint_id)
        total, succeeded, p50, p95 = (await self.session.execute(stmt)).one()
        return LatencySummary(
            total=total,
            succeeded=succeeded,
            p50_ms=float(p50) if p50 is not None else None,
            p95_ms=float(p95) if p95 is not None else None,
        )

    async def series(
        self,
        app_id: str,
        *,
        endpoint_id: str | None,
        since: datetime,
        bucket: timedelta,
    ) -> list[BucketRow]:
        bucket_ts = func.date_bin(bucket, Attempt.started_at, since).label("ts")
        stmt = (
            select(
                bucket_ts,
                func.count(),
                func.count().filter(Attempt.outcome == AttemptOutcome.SUCCEEDED.value),
                func.percentile_cont(0.5).within_group(Attempt.latency_ms),
                func.percentile_cont(0.95).within_group(Attempt.latency_ms),
            )
            .where(Attempt.app_id == app_id, Attempt.started_at >= since)
            .group_by(bucket_ts)
            .order_by(bucket_ts)
        )
        if endpoint_id is not None:
            stmt = stmt.where(Attempt.endpoint_id == endpoint_id)
        return [
            BucketRow(
                ts=ts,
                total=total,
                succeeded=ok,
                p50_ms=float(p50) if p50 is not None else None,
                p95_ms=float(p95) if p95 is not None else None,
            )
            for ts, total, ok, p50, p95 in await self.session.execute(stmt)
        ]

    async def endpoint_health(
        self, app_id: str, since: datetime, degraded_failure_rate: float
    ) -> EndpointHealthRow:
        """Classify every live endpoint in one aggregate: disabled, breaker not closed, or
        failing more than ``degraded_failure_rate`` of its attempts since ``since``."""
        failure_rate = (
            select(
                Attempt.endpoint_id.label("endpoint_id"),
                func.avg(cast(Attempt.outcome != AttemptOutcome.SUCCEEDED.value, Integer)).label(
                    "rate"
                ),
            )
            .where(Attempt.app_id == app_id, Attempt.started_at >= since)
            .group_by(Attempt.endpoint_id)
            .subquery()
        )
        disabled = Endpoint.disabled.is_(True)
        tripped = and_(~disabled, func.coalesce(BreakerStateRow.state, "closed") != "closed")
        degraded = and_(
            ~disabled,
            func.coalesce(BreakerStateRow.state, "closed") == "closed",
            func.coalesce(failure_rate.c.rate, 0) > degraded_failure_rate,
        )
        stmt = (
            select(
                func.count(),
                func.count().filter(disabled),
                func.count().filter(tripped),
                func.count().filter(degraded),
            )
            .select_from(Endpoint)
            .outerjoin(BreakerStateRow, BreakerStateRow.endpoint_id == Endpoint.id)
            .outerjoin(failure_rate, failure_rate.c.endpoint_id == Endpoint.id)
            .where(Endpoint.app_id == app_id, Endpoint.deleted_at.is_(None))
        )
        total, disabled_count, open_count, degraded_count = (await self.session.execute(stmt)).one()
        return EndpointHealthRow(
            total=total, disabled=disabled_count, open=open_count, degraded=degraded_count
        )
