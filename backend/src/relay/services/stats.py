from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from relay.auth.rbac import Principal
from relay.clock import Clock
from relay.domain.enums import DeliveryStatus
from relay.domain.errors import NotFoundError
from relay.domain.models import (
    AppOverviewOut,
    EndpointHealthCounts,
    LatencyStats,
    StatsBucket,
    StatsWindow,
)
from relay.persistence.repositories.activity import (
    AttemptRepository,
    BucketRow,
    DeliveryRepository,
    MessageRepository,
)
from relay.persistence.repositories.catalog import EndpointRepository
from relay.services.access import load_app

WINDOWS: dict[StatsWindow, tuple[timedelta, timedelta]] = {
    "1h": (timedelta(hours=1), timedelta(minutes=2)),
    "24h": (timedelta(hours=24), timedelta(minutes=30)),
    "7d": (timedelta(days=7), timedelta(hours=6)),
}

# An endpoint failing more than this share of its attempts in the window is degraded.
DEGRADED_FAILURE_RATE = 0.2


def _align(now: datetime, span: timedelta, bucket: timedelta) -> datetime:
    """Start of the window, snapped to a bucket boundary so buckets are stable across polls."""
    epoch = datetime(2000, 1, 1, tzinfo=now.tzinfo)
    start = now - span
    return epoch + ((start - epoch) // bucket) * bucket


def _fill(
    rows: list[BucketRow], start: datetime, end: datetime, bucket: timedelta
) -> list[StatsBucket]:
    by_ts = {row.ts: row for row in rows}
    series: list[StatsBucket] = []
    ts = start
    while ts <= end:
        row = by_ts.get(ts)
        series.append(
            StatsBucket(
                ts=ts,
                total=row.total if row else 0,
                succeeded=row.succeeded if row else 0,
                failed=(row.total - row.succeeded) if row else 0,
                p50_ms=row.p50_ms if row else None,
                p95_ms=row.p95_ms if row else None,
            )
        )
        ts += bucket
    return series


class StatsService:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.session = session
        self.clock = clock
        self.attempts = AttemptRepository(session)

    async def _latency(
        self, app_id: str, endpoint_id: str | None, window: StatsWindow, now: datetime
    ) -> LatencyStats:
        span, bucket = WINDOWS[window]
        start = _align(now, span, bucket)
        summary = await self.attempts.summary(app_id, endpoint_id=endpoint_id, since=start)
        rows = await self.attempts.series(
            app_id, endpoint_id=endpoint_id, since=start, bucket=bucket
        )
        return LatencyStats(
            window=window,
            total=summary.total,
            succeeded=summary.succeeded,
            failed=summary.total - summary.succeeded,
            success_rate=summary.succeeded / summary.total if summary.total else None,
            p50_ms=summary.p50_ms,
            p95_ms=summary.p95_ms,
            series=_fill(rows, start, now, bucket),
        )

    async def endpoint(
        self, principal: Principal, app_id: str, endpoint_id: str, window: StatsWindow
    ) -> LatencyStats:
        await load_app(self.session, principal, app_id)
        if await EndpointRepository(self.session).get(app_id, endpoint_id) is None:
            raise NotFoundError(f"endpoint {endpoint_id} not found")
        return await self._latency(app_id, endpoint_id, window, self.clock.now())

    async def overview(
        self, principal: Principal, app_id: str, window: StatsWindow
    ) -> AppOverviewOut:
        await load_app(self.session, principal, app_id)
        now = self.clock.now()
        span, bucket = WINDOWS[window]
        since = _align(now, span, bucket)
        latency = await self._latency(app_id, None, window, now)
        counts = await DeliveryRepository(self.session).unsettled_counts(app_id)
        messages = await MessageRepository(self.session).count_since(app_id, since)
        health = await self.attempts.endpoint_health(app_id, since, DEGRADED_FAILURE_RATE)
        return AppOverviewOut(
            **latency.model_dump(),
            messages=messages,
            pending=counts.get(DeliveryStatus.PENDING.value, 0),
            dead=counts.get(DeliveryStatus.DEAD.value, 0),
            endpoints=EndpointHealthCounts(
                total=health.total,
                healthy=health.total - health.disabled - health.open - health.degraded,
                degraded=health.degraded,
                open=health.open,
                disabled=health.disabled,
            ),
        )
