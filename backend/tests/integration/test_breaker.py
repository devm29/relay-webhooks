import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from relay.config import Settings
from relay.dispatcher.runner import Dispatcher
from relay.persistence.tables import BreakerStateRow, Endpoint
from relay.services.catalog import EndpointService
from tests.integration.conftest import (
    EndpointFactory,
    Publisher,
    Receiver,
    TenantFactory,
    fetch_attempts,
    fetch_deliveries,
)
from tests.support import FakeClock

pytestmark = pytest.mark.integration


async def _breaker(sessions: async_sessionmaker[AsyncSession], endpoint_id: str) -> BreakerStateRow:
    async with sessions() as session:
        row = await session.get(BreakerStateRow, endpoint_id)
        assert row is not None
        return row


async def test_breaker_opens_parks_traffic_probes_and_recovers(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    dispatcher: Dispatcher,
    receiver: Receiver,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
    settings: Settings,
) -> None:
    tenant = await make_tenant()
    endpoint = await make_endpoint(tenant)
    receiver.default = httpx.Response(500)

    for n in range(settings.breaker_failure_threshold):
        await publish(tenant, payload={"n": n})
    await dispatcher.run_until_idle()

    breaker = await _breaker(sessions, endpoint.id)
    assert breaker.state == "open"
    assert breaker.trip_count == 1

    for n in range(5):
        await publish(tenant, payload={"queued": n})
    sent_before = len(receiver.requests)
    assert await dispatcher.run_until_idle() == 0
    assert len(receiver.requests) == sent_before

    receiver.default = httpx.Response(200)
    assert breaker.open_until is not None
    clock.set(breaker.open_until)
    clock.advance(seconds=1)
    await dispatcher.run_until_idle()

    assert (await _breaker(sessions, endpoint.id)).state == "closed"
    # The successful probe pulls the parked backlog forward instead of waiting out backoff.
    clock.advance(seconds=1)
    await dispatcher.run_until_idle()
    deliveries = await fetch_deliveries(sessions)
    assert sum(d.status == "succeeded" for d in deliveries) == len(deliveries)


async def test_repeated_trips_auto_disable_and_enable_resets(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    dispatcher: Dispatcher,
    receiver: Receiver,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
    settings: Settings,
) -> None:
    tenant = await make_tenant()
    endpoint = await make_endpoint(tenant)
    receiver.default = httpx.Response(502)

    for n in range(settings.breaker_failure_threshold + 4):
        await publish(tenant, payload={"n": n})
    await dispatcher.run_until_idle()

    for _ in range(settings.breaker_disable_after_trips - 1):
        breaker = await _breaker(sessions, endpoint.id)
        assert breaker.state == "open" and breaker.open_until is not None
        clock.set(breaker.open_until)
        clock.advance(seconds=1)
        await dispatcher.run_until_idle()

    async with sessions() as session:
        row = await session.get(Endpoint, endpoint.id)
        assert row is not None
        assert row.disabled
        assert row.disabled_reason is not None and "circuit breaker" in row.disabled_reason

    attempts_before = len(await fetch_attempts(sessions))
    clock.advance(hours=1)
    assert await dispatcher.run_until_idle() == 0

    receiver.default = httpx.Response(200)
    async with sessions() as session:
        enabled = await EndpointService(session, settings, clock).enable(
            tenant.owner, tenant.app_id, endpoint.id
        )
    assert not enabled.disabled
    assert enabled.breaker is not None and enabled.breaker.state == "closed"
    await dispatcher.run_until_idle()
    assert len(await fetch_attempts(sessions)) > attempts_before
