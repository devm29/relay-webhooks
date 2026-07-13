"""Fans Postgres NOTIFY payloads out to in-process subscribers (SSE streams, idle workers).

One dedicated asyncpg connection per process LISTENs; subscribers get bounded queues
so a slow browser tab can only drop its own events, never stall the listener.
"""

import asyncio
import contextlib
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from typing import Any

import asyncpg
from pydantic import ValidationError

from relay.domain.models import LiveEvent
from relay.events.notify import LIVE_CHANNEL
from relay.logging import get_logger

log = get_logger(__name__)

_QUEUE_SIZE = 512
_RECONNECT_DELAY_SECONDS = 2.0


class PgListener:
    def __init__(self, dsn: str, channels: dict[str, Callable[[str], None]]) -> None:
        self._dsn = dsn
        self._channels = channels
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="pg-listener")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        while not self._stopping.is_set():
            conn: Any = None
            try:
                conn = await asyncpg.connect(self._dsn)
                closed = asyncio.Event()
                conn.add_termination_listener(lambda _c, done=closed: done.set())
                for channel, handler in self._channels.items():
                    await conn.add_listener(channel, self._adapter(handler))
                log.info("listener.connected", channels=list(self._channels))
                await closed.wait()
                log.warning("listener.disconnected")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("listener.error", error=str(exc))
            finally:
                if conn is not None and not conn.is_closed():
                    await conn.close()
            await asyncio.sleep(_RECONNECT_DELAY_SECONDS)

    @staticmethod
    def _adapter(handler: Callable[[str], None]) -> Callable[[Any, int, str, str], None]:
        def callback(_conn: Any, _pid: int, _channel: str, payload: str) -> None:
            handler(payload)

        return callback


class LiveHub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[LiveEvent]]] = defaultdict(set)

    def handle(self, payload: str) -> None:
        try:
            event = LiveEvent.model_validate_json(payload)
        except ValidationError:
            log.warning("hub.bad_payload")
            return
        for queue in list(self._subscribers.get(event.app_id, ())):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    @contextlib.asynccontextmanager
    async def subscribe(self, app_id: str) -> AsyncIterator[asyncio.Queue[LiveEvent]]:
        queue: asyncio.Queue[LiveEvent] = asyncio.Queue(maxsize=_QUEUE_SIZE)
        self._subscribers[app_id].add(queue)
        try:
            yield queue
        finally:
            self._subscribers[app_id].discard(queue)
            if not self._subscribers[app_id]:
                del self._subscribers[app_id]

    def subscriber_count(self) -> int:
        return sum(len(queues) for queues in self._subscribers.values())


def live_listener(dsn: str, hub: LiveHub) -> PgListener:
    return PgListener(dsn, {LIVE_CHANNEL: hub.handle})
