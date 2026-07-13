import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from relay.config import Settings
from relay.domain.models import LiveEvent
from relay.events.hub import LiveHub, live_listener
from relay.events.notify import publish_live

pytestmark = pytest.mark.integration


def _event(app_id: str, ident: str) -> LiveEvent:
    return LiveEvent(
        kind="message",
        app_id=app_id,
        id=ident,
        message_id=ident,
        event_type="ping",
        at=datetime.now(UTC),
    )


async def test_notify_reaches_only_matching_subscribers_and_only_on_commit(
    sessions: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    hub = LiveHub()
    listener = live_listener(settings.asyncpg_dsn, hub)
    await listener.start()
    try:
        async with hub.subscribe("app_a") as mine, hub.subscribe("app_b") as theirs:
            await asyncio.sleep(0.3)

            async with sessions() as session:
                await publish_live(session, _event("app_a", "msg_rolled_back"))
                await session.rollback()
            async with sessions() as session:
                await publish_live(session, _event("app_a", "msg_committed"))
                await session.commit()

            received = await asyncio.wait_for(mine.get(), timeout=5)
            assert received.id == "msg_committed"
            await asyncio.sleep(0.2)
            assert mine.empty()
            assert theirs.empty()
            assert hub.subscriber_count() == 2
        assert hub.subscriber_count() == 0
    finally:
        await listener.stop()
