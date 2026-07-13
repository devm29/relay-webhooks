from datetime import datetime

from sqlalchemy import CursorResult, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from relay.domain.breaker import BreakerSnapshot
from relay.domain.enums import BreakerState
from relay.persistence.repositories.base import paginate_desc, split_page
from relay.persistence.tables import BreakerStateRow, Endpoint, EndpointSecret, EventType


class EventTypeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, event_type: EventType) -> EventType:
        self.session.add(event_type)
        await self.session.flush()
        return event_type

    async def get(self, app_id: str, name: str) -> EventType | None:
        stmt = select(EventType).where(EventType.app_id == app_id, EventType.name == name)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def existing_names(self, app_id: str, names: list[str]) -> set[str]:
        if not names:
            return set()
        stmt = select(EventType.name).where(EventType.app_id == app_id, EventType.name.in_(names))
        return set((await self.session.execute(stmt)).scalars())

    async def list_all(self, app_id: str, *, include_archived: bool) -> list[EventType]:
        stmt = select(EventType).where(EventType.app_id == app_id)
        if not include_archived:
            stmt = stmt.where(EventType.archived.is_(False))
        return list((await self.session.execute(stmt.order_by(EventType.name))).scalars())

    async def delete(self, event_type: EventType) -> None:
        await self.session.delete(event_type)


class EndpointRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, endpoint: Endpoint, secret: EndpointSecret) -> Endpoint:
        self.session.add(endpoint)
        await self.session.flush()
        self.session.add_all([secret, BreakerStateRow(endpoint_id=endpoint.id)])
        await self.session.flush()
        return endpoint

    async def get(self, app_id: str, endpoint_id: str) -> Endpoint | None:
        stmt = select(Endpoint).where(
            Endpoint.app_id == app_id, Endpoint.id == endpoint_id, Endpoint.deleted_at.is_(None)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_page(
        self, app_id: str, *, before: str | None, limit: int
    ) -> tuple[list[Endpoint], str | None]:
        stmt = paginate_desc(
            select(Endpoint).where(Endpoint.app_id == app_id, Endpoint.deleted_at.is_(None)),
            Endpoint.id,
            before=before,
            limit=limit,
        )
        rows = list((await self.session.execute(stmt)).scalars())
        return split_page(rows, limit)

    async def soft_delete(self, endpoint: Endpoint, now: datetime) -> None:
        endpoint.deleted_at = now
        endpoint.disabled = True
        endpoint.disabled_reason = "endpoint deleted"
        endpoint.updated_at = now

    async def breakers(self, endpoint_ids: list[str]) -> dict[str, BreakerStateRow]:
        if not endpoint_ids:
            return {}
        stmt = select(BreakerStateRow).where(BreakerStateRow.endpoint_id.in_(endpoint_ids))
        return {row.endpoint_id: row for row in (await self.session.execute(stmt)).scalars()}

    async def breaker_snapshot(self, endpoint_id: str) -> BreakerSnapshot:
        """Unlocked read; callers that change state go through a fenced write."""
        stmt = select(BreakerStateRow).where(BreakerStateRow.endpoint_id == endpoint_id)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return read_breaker(row) if row is not None else BreakerSnapshot()

    async def lock_breaker(self, endpoint_id: str) -> BreakerStateRow:
        await ensure_breaker_row(self.session, endpoint_id)
        stmt = (
            select(BreakerStateRow)
            .where(BreakerStateRow.endpoint_id == endpoint_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def transition_breaker(
        self, endpoint_id: str, expected: BreakerSnapshot, new: BreakerSnapshot, now: datetime
    ) -> bool:
        """Compare-and-set, so only one worker wins the open -> half-open probe slot."""
        result = await self.session.execute(
            update(BreakerStateRow)
            .where(
                BreakerStateRow.endpoint_id == endpoint_id,
                BreakerStateRow.state == expected.state.value,
                BreakerStateRow.open_until.is_not_distinct_from(expected.open_until),
                BreakerStateRow.probe_started_at.is_not_distinct_from(expected.probe_started_at),
            )
            .values(**_breaker_values(new), updated_at=now)
            .execution_options(synchronize_session=False)
        )
        assert isinstance(result, CursorResult)
        return result.rowcount == 1

    async def close_breaker(self, endpoint_id: str, now: datetime) -> None:
        """Reset after a success. A no-op without row locks while the breaker is already
        clean, which is the steady state for a healthy endpoint."""
        await self.session.execute(
            update(BreakerStateRow)
            .where(
                BreakerStateRow.endpoint_id == endpoint_id,
                or_(
                    BreakerStateRow.state != BreakerState.CLOSED.value,
                    BreakerStateRow.consecutive_failures != 0,
                    BreakerStateRow.trip_count != 0,
                ),
            )
            .values(**_breaker_values(BreakerSnapshot()), updated_at=now)
            .execution_options(synchronize_session=False)
        )

    async def reset_breaker(self, endpoint_id: str, now: datetime) -> None:
        row = await self.lock_breaker(endpoint_id)
        write_breaker(row, BreakerSnapshot(), now)

    async def active_secrets(self, endpoint_id: str, now: datetime) -> list[EndpointSecret]:
        stmt = (
            select(EndpointSecret)
            .where(
                EndpointSecret.endpoint_id == endpoint_id,
                or_(EndpointSecret.expires_at.is_(None), EndpointSecret.expires_at > now),
            )
            .order_by(EndpointSecret.created_at.desc(), EndpointSecret.id.desc())
        )
        return list((await self.session.execute(stmt)).scalars())

    async def rotate_secret(
        self, endpoint_id: str, new_secret: EndpointSecret, retire_at: datetime
    ) -> None:
        await self.session.execute(
            update(EndpointSecret)
            .where(
                EndpointSecret.endpoint_id == endpoint_id,
                or_(EndpointSecret.expires_at.is_(None), EndpointSecret.expires_at > retire_at),
            )
            .values(expires_at=retire_at)
        )
        self.session.add(new_secret)
        await self.session.flush()

    async def disable(self, endpoint_id: str, reason: str, now: datetime) -> None:
        await self.session.execute(
            update(Endpoint)
            .where(Endpoint.id == endpoint_id)
            .values(disabled=True, disabled_reason=reason, updated_at=now)
        )


async def ensure_breaker_row(session: AsyncSession, endpoint_id: str) -> None:
    await session.execute(
        pg_insert(BreakerStateRow)
        .values(endpoint_id=endpoint_id)
        .on_conflict_do_nothing(index_elements=[BreakerStateRow.endpoint_id])
    )


def _breaker_values(snap: BreakerSnapshot) -> dict[str, object]:
    return {
        "state": snap.state.value,
        "consecutive_failures": snap.consecutive_failures,
        "trip_count": snap.trip_count,
        "opened_at": snap.opened_at,
        "open_until": snap.open_until,
        "probe_started_at": snap.probe_started_at,
    }


def read_breaker(row: BreakerStateRow) -> BreakerSnapshot:
    return BreakerSnapshot(
        state=BreakerState(row.state),
        consecutive_failures=row.consecutive_failures,
        trip_count=row.trip_count,
        opened_at=row.opened_at,
        open_until=row.open_until,
        probe_started_at=row.probe_started_at,
    )


def write_breaker(row: BreakerStateRow, snap: BreakerSnapshot, now: datetime) -> None:
    row.state = snap.state.value
    row.consecutive_failures = snap.consecutive_failures
    row.trip_count = snap.trip_count
    row.opened_at = snap.opened_at
    row.open_until = snap.open_until
    row.probe_started_at = snap.probe_started_at
    row.updated_at = now
