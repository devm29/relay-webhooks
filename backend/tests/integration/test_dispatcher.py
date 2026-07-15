import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from relay.config import Settings
from relay.dispatcher.runner import Dispatcher
from relay.domain.errors import ConflictError, NotFoundError
from relay.domain.models import BulkReplayIn, RotateSecretIn
from relay.domain.retry import RetryPolicy, backoff_ceiling
from relay.persistence import queue
from relay.persistence.tables import BreakerStateRow, Delivery, Endpoint
from relay.services.catalog import EndpointService
from relay.services.messages import DeliveryService
from relay.signing import Webhook, WebhookVerificationError
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


async def _advance_to_next_attempt(
    sessions: async_sessionmaker[AsyncSession], clock: FakeClock, delivery_id: str
) -> None:
    [delivery] = await fetch_deliveries(sessions, id=delivery_id)
    assert delivery.next_attempt_at is not None
    clock.set(delivery.next_attempt_at)


async def test_successful_delivery_is_signed_and_recorded(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    dispatcher: Dispatcher,
    receiver: Receiver,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
) -> None:
    tenant = await make_tenant()
    secret = "whsec_" + "c2VjcmV0LXNlY3JldC1zZWNyZXQtc2VjcmV0"
    await make_endpoint(tenant, secret=secret, headers={"x-team": "billing"})
    message = await publish(tenant, payload={"invoice_id": "in_9", "amount": 4200})

    assert await dispatcher.run_until_idle() == 1

    [request] = receiver.requests
    assert request.headers["webhook-id"] == message.id
    assert request.headers["x-team"] == "billing"
    Webhook(secret).verify(request.content, dict(request.headers), now=clock.now())
    body = json.loads(request.content)
    assert body == {
        "type": "invoice.paid",
        "timestamp": message.created_at.isoformat(),
        "data": {"invoice_id": "in_9", "amount": 4200},
    }

    [delivery] = await fetch_deliveries(sessions, message_id=message.id)
    assert delivery.status == "succeeded"
    assert delivery.lease_token is None
    [attempt] = await fetch_attempts(sessions, delivery_id=delivery.id)
    assert (attempt.outcome, attempt.status_code, attempt.attempt_number) == ("succeeded", 200, 1)
    assert attempt.response_snippet == '{"ok":true}'


async def test_failures_follow_the_backoff_schedule_then_dead_letter(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    dispatcher: Dispatcher,
    receiver: Receiver,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
    retry_policy: RetryPolicy,
    settings: Settings,
) -> None:
    receiver.default = httpx.Response(500, text="boom")
    tenant = await make_tenant()
    await make_endpoint(tenant)
    message = await publish(tenant)
    [delivery] = await fetch_deliveries(sessions, message_id=message.id)

    for attempt in range(1, settings.retry_max_attempts):
        before = clock.now()
        assert await dispatcher.run_until_idle() == 1
        [row] = await fetch_deliveries(sessions, id=delivery.id)
        assert row.status == "pending"
        assert row.attempt_count == attempt
        assert row.next_attempt_at is not None
        delay = (row.next_attempt_at - before).total_seconds()
        assert 0 <= delay <= backoff_ceiling(retry_policy, attempt)
        assert await dispatcher.run_until_idle() == 0
        clock.set(row.next_attempt_at)
        # The breaker would otherwise open after three straight failures and park the retry.
        async with sessions() as session, session.begin():
            row_b = await session.get(BreakerStateRow, row.endpoint_id)
            assert row_b is not None
            row_b.state, row_b.consecutive_failures = "closed", 0

    assert await dispatcher.run_until_idle() == 1
    [dead] = await fetch_deliveries(sessions, id=delivery.id)
    assert dead.status == "dead"
    assert dead.next_attempt_at is None
    assert dead.last_status_code == 500
    attempts = await fetch_attempts(sessions, delivery_id=delivery.id)
    assert [a.attempt_number for a in attempts] == list(range(1, settings.retry_max_attempts + 1))
    assert all(a.outcome == "failed" for a in attempts)


async def test_retry_after_header_is_honoured(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    dispatcher: Dispatcher,
    receiver: Receiver,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
) -> None:
    receiver.queue(httpx.Response(429, headers={"retry-after": "300"}))
    tenant = await make_tenant()
    await make_endpoint(tenant)
    message = await publish(tenant)

    started = clock.now()
    await dispatcher.run_until_idle()
    [delivery] = await fetch_deliveries(sessions, message_id=message.id)
    assert delivery.next_attempt_at is not None
    assert delivery.next_attempt_at >= started + timedelta(seconds=300)


async def test_gone_disables_the_endpoint_and_dead_letters(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    dispatcher: Dispatcher,
    receiver: Receiver,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    receiver.default = httpx.Response(410)
    tenant = await make_tenant()
    endpoint = await make_endpoint(tenant)
    message = await publish(tenant)

    await dispatcher.run_until_idle()

    [delivery] = await fetch_deliveries(sessions, message_id=message.id)
    assert delivery.status == "dead"
    async with sessions() as session:
        row = await session.get(Endpoint, endpoint.id)
        assert row is not None
        assert row.disabled and row.disabled_reason == "endpoint responded 410 Gone"


async def test_replay_single_and_bulk(
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
    receiver.default = httpx.Response(503)
    for n in range(3):
        await publish(tenant, payload={"n": n})
    async with sessions() as session, session.begin():
        await session.execute(
            update(Delivery).values(schedule_index=settings.retry_max_attempts - 1)
        )

    await dispatcher.run_until_idle()
    dead = await fetch_deliveries(sessions, status="dead")
    assert len(dead) == 3

    receiver.default = httpx.Response(204)
    async with sessions() as session:
        await DeliveryService(session, clock).replay(tenant.owner, tenant.app_id, dead[0].id)
    # Three straight failures opened the breaker, so the replay waits to become the probe.
    assert await dispatcher.run_until_idle() == 0
    clock.advance(seconds=settings.breaker_base_cooldown_seconds + 1)
    assert await dispatcher.run_until_idle() == 1
    [replayed] = await fetch_deliveries(sessions, id=dead[0].id)
    assert replayed.status == "succeeded"
    last = (await fetch_attempts(sessions, delivery_id=replayed.id))[-1]
    assert last.trigger == "replay"
    assert last.attempt_number == 2

    async with sessions() as session:
        count = await DeliveryService(session, clock).replay_bulk(
            tenant.owner, tenant.app_id, BulkReplayIn(endpoint_id=endpoint.id, status="dead")
        )
    assert count == 2
    await dispatcher.run_until_idle()
    assert len(await fetch_deliveries(sessions, status="succeeded")) == 3


async def test_secret_rotation_signs_with_both_secrets_during_overlap(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    dispatcher: Dispatcher,
    receiver: Receiver,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    clock: FakeClock,
) -> None:
    old = "whsec_" + "b2xkLXNlY3JldC1vbGQtc2VjcmV0LW9sZA=="
    new = "whsec_" + "bmV3LXNlY3JldC1uZXctc2VjcmV0LW5ldw=="
    tenant = await make_tenant()
    endpoint = await make_endpoint(tenant, secret=old)
    async with sessions() as session:
        secrets = await EndpointService(session, settings, clock).rotate_secret(
            tenant.owner,
            tenant.app_id,
            endpoint.id,
            RotateSecretIn(secret=new, overlap_seconds=3600),
        )
    assert secrets.current.secret == new
    assert [s.secret for s in secrets.previous] == [old]

    await publish(tenant, payload={"n": 1})
    await dispatcher.run_until_idle()
    during = receiver.requests[-1]
    assert len(during.headers["webhook-signature"].split(" ")) == 2
    for secret in (old, new):
        Webhook(secret).verify(during.content, dict(during.headers), now=clock.now())

    clock.advance(hours=2)
    await publish(tenant, payload={"n": 2})
    await dispatcher.run_until_idle()
    after = receiver.requests[-1]
    Webhook(new).verify(after.content, dict(after.headers), now=clock.now())
    with pytest.raises(WebhookVerificationError):
        Webhook(old).verify(after.content, dict(after.headers), now=clock.now())


async def test_rate_limited_endpoint_defers_without_burning_attempts(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    dispatcher: Dispatcher,
    receiver: Receiver,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    tenant = await make_tenant()
    await make_endpoint(tenant, rate_limit_per_second=1)
    for n in range(3):
        await publish(tenant, payload={"n": n})

    await dispatcher.run_until_idle()

    assert len(receiver.requests) == 1
    deliveries = await fetch_deliveries(sessions)
    assert sorted(d.status for d in deliveries) == ["pending", "pending", "succeeded"]
    assert all(d.attempt_count == 0 for d in deliveries if d.status == "pending")
    assert len(await fetch_attempts(sessions)) == 1


async def test_pending_delivery_waiting_for_a_retry_can_be_replayed(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    dispatcher: Dispatcher,
    receiver: Receiver,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
) -> None:
    tenant = await make_tenant()
    await make_endpoint(tenant)
    receiver.queue(httpx.Response(500))
    message = await publish(tenant)
    await dispatcher.run_until_idle()

    [waiting] = await fetch_deliveries(sessions, message_id=message.id)
    assert waiting.status == "pending"
    assert waiting.lease_until is None
    assert waiting.next_attempt_at is not None and waiting.next_attempt_at > clock.now()

    async with sessions() as session:
        replayed = await DeliveryService(session, clock).replay(
            tenant.owner, tenant.app_id, waiting.id
        )
    assert replayed.next_attempt_at == clock.now()

    assert await dispatcher.run_until_idle() == 1
    [done] = await fetch_deliveries(sessions, id=waiting.id)
    assert done.status == "succeeded"


async def test_delivery_in_flight_cannot_be_replayed(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
) -> None:
    tenant = await make_tenant()
    await make_endpoint(tenant)
    message = await publish(tenant)
    async with sessions() as session, session.begin():
        [job] = await queue.lease_due(
            session, now=clock.now(), lease_for=timedelta(seconds=60), limit=1
        )
    assert job.message_id == message.id

    async with sessions() as session:
        with pytest.raises(ConflictError, match="being attempted"):
            await DeliveryService(session, clock).replay(
                tenant.owner, tenant.app_id, job.delivery_id
            )


async def test_rate_limited_backlog_does_not_hold_up_other_endpoints(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    dispatcher: Dispatcher,
    receiver: Receiver,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
) -> None:
    tenant = await make_tenant(event_types=("audit.logged", "order.created"))
    slow = await make_endpoint(
        tenant,
        url="https://slow.example.com/hook",
        event_types=["audit.logged"],
        rate_limit_per_second=1,
    )
    await make_endpoint(tenant, url="https://fast.example.com/hook", event_types=["order.created"])
    for n in range(20):
        await publish(tenant, event_type="audit.logged", payload={"n": n})
    published_at = clock.now()
    clock.advance(milliseconds=1)
    for n in range(3):
        await publish(tenant, event_type="order.created", payload={"n": n})

    await dispatcher.run_until_idle()

    hosts = [request.url.host for request in receiver.requests]
    assert hosts.count("fast.example.com") == 3
    assert hosts.count("slow.example.com") == 1

    backlog = await fetch_deliveries(sessions, endpoint_id=slow.id, status="pending")
    assert len(backlog) == 19
    # Held back by the lease query itself: no attempts burnt, no rows rescheduled or rewritten.
    assert all(d.attempt_count == 0 and d.lease_token is None for d in backlog)
    assert all(d.next_attempt_at == published_at for d in backlog)
    assert all(d.updated_at == published_at for d in backlog)

    clock.advance(seconds=1)
    await dispatcher.run_until_idle()
    assert [r.url.host for r in receiver.requests].count("slow.example.com") == 2


async def test_healthy_traffic_does_not_rewrite_the_breaker_row(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    dispatcher: Dispatcher,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    tenant = await make_tenant()
    endpoint = await make_endpoint(tenant)
    async with sessions() as session:
        before = await session.get(BreakerStateRow, endpoint.id)
        assert before is not None
        stamp = before.updated_at

    for n in range(5):
        await publish(tenant, payload={"n": n})
    assert await dispatcher.run_until_idle() == 5

    async with sessions() as session:
        after = await session.get(BreakerStateRow, endpoint.id)
        assert after is not None
        assert after.updated_at == stamp


async def test_result_from_a_lost_lease_is_kept_but_does_not_touch_the_breaker(
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
    await publish(tenant)
    async with sessions() as session, session.begin():
        [stale] = await queue.lease_due(
            session, now=clock.now(), lease_for=timedelta(seconds=60), limit=1
        )
    clock.advance(seconds=61)
    async with sessions() as session, session.begin():
        [fresh] = await queue.lease_due(
            session, now=clock.now(), lease_for=timedelta(seconds=60), limit=1
        )
    assert fresh.delivery_id == stale.delivery_id

    receiver.default = httpx.Response(500)
    processor = dispatcher._processor
    for _ in range(settings.breaker_failure_threshold):
        await processor.process(stale)

    assert len(await fetch_attempts(sessions, delivery_id=stale.delivery_id)) == (
        settings.breaker_failure_threshold
    )
    async with sessions() as session:
        breaker = await session.get(BreakerStateRow, endpoint.id)
        assert breaker is not None
        assert (breaker.state, breaker.consecutive_failures) == ("closed", 0)
    [delivery] = await fetch_deliveries(sessions, id=stale.delivery_id)
    assert delivery.lease_token == fresh.lease_token
    assert delivery.attempt_count == 0


async def test_deleting_an_endpoint_keeps_its_history(
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
    await publish(tenant, payload={"n": 1})
    await dispatcher.run_until_idle()
    receiver.default = httpx.Response(500)
    await publish(tenant, payload={"n": 2})
    await dispatcher.run_until_idle()

    async with sessions() as session:
        await EndpointService(session, settings, clock).delete(
            tenant.owner, tenant.app_id, endpoint.id
        )

    statuses = sorted(d.status for d in await fetch_deliveries(sessions, endpoint_id=endpoint.id))
    assert statuses == ["dead", "succeeded"]
    assert len(await fetch_attempts(sessions, endpoint_id=endpoint.id)) == 2

    async with sessions() as session:
        with pytest.raises(NotFoundError):
            await EndpointService(session, settings, clock).get(
                tenant.owner, tenant.app_id, endpoint.id
            )
        listed, _ = await EndpointService(session, settings, clock).list_page(
            tenant.owner, tenant.app_id, before=None, limit=10
        )
        assert listed == []
    assert (await publish(tenant, payload={"n": 3})).fanout == 0

    [dead] = await fetch_deliveries(sessions, endpoint_id=endpoint.id, status="dead")
    async with sessions() as session:
        with pytest.raises(ConflictError, match="deleted"):
            await DeliveryService(session, clock).replay(tenant.owner, tenant.app_id, dead.id)
        replayed = await DeliveryService(session, clock).replay_bulk(
            tenant.owner, tenant.app_id, BulkReplayIn(status="dead")
        )
    assert replayed == 0
