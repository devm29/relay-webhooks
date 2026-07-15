import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from relay.persistence import queue
from relay.persistence.tables import BreakerStateRow, Delivery
from tests.integration.conftest import EndpointFactory, Publisher, TenantFactory
from tests.support import FakeClock

pytestmark = pytest.mark.integration

LEASE = timedelta(seconds=60)


async def _lease(
    sessions: async_sessionmaker[AsyncSession], clock: FakeClock, limit: int = 10
) -> list[queue.DeliveryJob]:
    async with sessions() as session, session.begin():
        return await queue.lease_due(session, now=clock.now(), lease_for=LEASE, limit=limit)


async def test_concurrent_workers_never_lease_the_same_delivery(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
) -> None:
    tenant = await make_tenant()
    for _ in range(3):
        await make_endpoint(tenant)
    for n in range(80):
        await publish(tenant, payload={"n": n})

    leased: list[str] = []

    async def worker() -> None:
        while jobs := await _lease(sessions, clock, limit=3):
            leased.extend(job.delivery_id for job in jobs)
            await asyncio.sleep(0)

    await asyncio.gather(*(worker() for _ in range(12)))

    assert len(leased) == 240
    assert len(set(leased)) == 240


async def test_expired_lease_is_reclaimed_and_the_stale_owner_is_fenced_out(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
) -> None:
    tenant = await make_tenant()
    await make_endpoint(tenant)
    await publish(tenant)

    [first] = await _lease(sessions, clock)
    clock.advance(seconds=30)
    assert await _lease(sessions, clock) == []

    clock.advance(seconds=31)
    [second] = await _lease(sessions, clock)
    assert second.delivery_id == first.delivery_id
    assert second.lease_token != first.lease_token

    async with sessions() as session, session.begin():
        assert not await queue.mark_succeeded(session, first, status_code=200, now=clock.now())
        assert await queue.mark_succeeded(session, second, status_code=200, now=clock.now())


async def test_only_due_deliveries_on_healthy_endpoints_are_leased(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
) -> None:
    tenant = await make_tenant()
    healthy = await make_endpoint(tenant)
    tripped = await make_endpoint(tenant)
    await publish(tenant)

    async with sessions() as session, session.begin():
        await session.execute(
            update(BreakerStateRow)
            .where(BreakerStateRow.endpoint_id == tripped.id)
            .values(state="open", open_until=clock.now() + timedelta(minutes=1))
        )
        await session.execute(
            update(Delivery)
            .where(Delivery.endpoint_id == healthy.id)
            .values(next_attempt_at=clock.now() + timedelta(seconds=5))
        )

    assert await _lease(sessions, clock) == []
    clock.advance(seconds=6)
    assert [j.endpoint_id for j in await _lease(sessions, clock)] == [healthy.id]
    clock.advance(seconds=55)
    assert [j.endpoint_id for j in await _lease(sessions, clock)] == [tripped.id]
