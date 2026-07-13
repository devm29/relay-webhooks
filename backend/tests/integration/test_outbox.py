import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from relay.domain.errors import ConflictError, ValidationFailedError
from relay.domain.models import EventTypeCreateIn, MessageCreateIn
from relay.persistence.tables import Delivery, Message
from relay.services import messages as messages_module
from relay.services.catalog import EventTypeService
from relay.services.messages import MessageService
from tests.integration.conftest import (
    EndpointFactory,
    Publisher,
    TenantFactory,
    fetch_deliveries,
)
from tests.support import FakeClock

pytestmark = pytest.mark.integration


async def _count(sessions: async_sessionmaker[AsyncSession], model: type) -> int:
    async with sessions() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_fanout_respects_event_filters_and_disabled_endpoints(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    tenant = await make_tenant(event_types=("invoice.paid", "user.created"))
    all_events = await make_endpoint(tenant)
    invoices = await make_endpoint(tenant, event_types=["invoice.paid"])
    await make_endpoint(tenant, event_types=["user.created"])
    await make_endpoint(tenant, disabled=True)

    result = await publish(tenant, "invoice.paid")

    assert result.fanout == 2
    deliveries = await fetch_deliveries(sessions, message_id=result.id)
    assert {d.endpoint_id for d in deliveries} == {all_events.id, invoices.id}
    assert all(d.status == "pending" and d.next_attempt_at is not None for d in deliveries)


async def test_message_and_deliveries_roll_back_together(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = await make_tenant()
    await make_endpoint(tenant)
    await make_endpoint(tenant)

    async def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("crash between outbox write and commit")

    monkeypatch.setattr(messages_module, "publish_live", explode)
    with pytest.raises(RuntimeError):
        async with sessions() as session:
            await MessageService(session, clock).publish(
                tenant.owner,
                tenant.app_id,
                MessageCreateIn(event_type="invoice.paid", payload={}),
                idempotency_key=None,
            )

    assert await _count(sessions, Message) == 0
    assert await _count(sessions, Delivery) == 0


async def test_concurrent_publishes_with_one_idempotency_key_create_one_message(
    make_tenant: TenantFactory,
    make_endpoint: EndpointFactory,
    publish: Publisher,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    tenant = await make_tenant()
    await make_endpoint(tenant)

    results = await asyncio.gather(
        *(publish(tenant, payload={"n": 1}, idempotency_key="order-42") for _ in range(12))
    )

    assert len({r.id for r in results}) == 1
    assert sum(not r.idempotent_replay for r in results) == 1
    assert await _count(sessions, Message) == 1
    assert await _count(sessions, Delivery) == 1


async def test_reusing_a_key_with_a_different_body_conflicts(
    make_tenant: TenantFactory, publish: Publisher
) -> None:
    tenant = await make_tenant()
    await publish(tenant, payload={"n": 1}, idempotency_key="k")
    with pytest.raises(ConflictError):
        await publish(tenant, payload={"n": 2}, idempotency_key="k")


async def test_payload_is_validated_against_the_registered_schema(
    make_tenant: TenantFactory,
    publish: Publisher,
    sessions: async_sessionmaker[AsyncSession],
    clock: FakeClock,
) -> None:
    tenant = await make_tenant(event_types=())
    async with sessions() as session:
        await EventTypeService(session, clock).create(
            tenant.owner,
            tenant.app_id,
            EventTypeCreateIn(
                name="invoice.paid",
                payload_schema={
                    "type": "object",
                    "required": ["invoice_id", "amount"],
                    "properties": {"amount": {"type": "integer", "minimum": 0}},
                },
            ),
        )

    with pytest.raises(ValidationFailedError) as excinfo:
        await publish(tenant, payload={"amount": -5})
    paths = {d["path"] for d in excinfo.value.details or []}
    assert paths == {"/", "/amount"}

    with pytest.raises(ValidationFailedError, match="unknown event type"):
        await publish(tenant, event_type="nope.never")

    ok = await publish(tenant, payload={"invoice_id": "in_1", "amount": 10})
    assert ok.fanout == 0
