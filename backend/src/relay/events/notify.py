from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from relay.domain.models import LiveEvent

LIVE_CHANNEL = "relay_live"
WAKE_CHANNEL = "relay_wake"


async def publish_live(session: AsyncSession, event: LiveEvent) -> None:
    """Queued with the surrounding transaction; Postgres only delivers it on commit."""
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": LIVE_CHANNEL, "payload": event.model_dump_json()},
    )


async def wake_dispatchers(session: AsyncSession) -> None:
    await session.execute(text("SELECT pg_notify(:channel, '')"), {"channel": WAKE_CHANNEL})
