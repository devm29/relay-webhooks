import asyncio
import contextlib
import os
import socket

from relay.dispatcher.processor import DeliveryProcessor
from relay.events.hub import PgListener
from relay.events.notify import WAKE_CHANNEL
from relay.logging import get_logger

log = get_logger(__name__)


class Dispatcher:
    """N cooperative workers in one process. Each leases one due delivery at a time;
    idle workers sleep until the poll interval elapses or an ingest NOTIFY wakes them."""

    def __init__(
        self,
        processor: DeliveryProcessor,
        *,
        workers: int,
        idle_poll_seconds: float,
        wake_dsn: str | None = None,
    ) -> None:
        self._processor = processor
        self._workers = workers
        self._idle_poll = idle_poll_seconds
        self._wake = asyncio.Event()
        self._stopping = asyncio.Event()
        self._listener = PgListener(wake_dsn, {WAKE_CHANNEL: self._on_wake}) if wake_dsn else None
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"

    def _on_wake(self, _payload: str) -> None:
        self._wake.set()
        self._wake.clear()

    def stop(self) -> None:
        self._stopping.set()
        self._on_wake("")

    async def run(self) -> None:
        if self._listener is not None:
            await self._listener.start()
        log.info("dispatcher.started", workers=self._workers, worker_id=self.worker_id)
        try:
            async with asyncio.TaskGroup() as group:
                for index in range(self._workers):
                    group.create_task(self._work(index), name=f"worker-{index}")
        finally:
            if self._listener is not None:
                await self._listener.stop()
            log.info("dispatcher.stopped")

    async def run_until_idle(self, *, max_rounds: int = 1000) -> int:
        """Drain everything currently due. Used by tests and one-shot tooling."""
        processed = 0
        for _ in range(max_rounds):
            jobs = await self._processor.lease(limit=self._workers)
            if not jobs:
                break
            await asyncio.gather(*(self._processor.process(job) for job in jobs))
            processed += len(jobs)
        return processed

    async def _work(self, index: int) -> None:
        while not self._stopping.is_set():
            try:
                jobs = await self._processor.lease(limit=1)
            except Exception:
                log.exception("dispatcher.lease_failed", worker=index)
                await self._idle()
                continue
            if not jobs:
                await self._idle()
                continue
            for job in jobs:
                try:
                    await self._processor.process(job)
                except Exception:
                    # The lease will lapse and another worker will pick the delivery up.
                    log.exception("dispatcher.process_failed", delivery_id=job.delivery_id)

    async def _idle(self) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout=self._idle_poll)
