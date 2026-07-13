import asyncio
import signal

from relay.clock import SystemClock
from relay.config import get_settings
from relay.delivery.client import WebhookSender, build_http_client
from relay.dispatcher.processor import DeliveryProcessor, Policies
from relay.dispatcher.runner import Dispatcher
from relay.logging import configure_logging
from relay.persistence.db import create_engine, create_session_factory


async def _main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.log_json)
    engine = create_engine(settings)
    async with build_http_client(allow_private=settings.private_endpoints_allowed) as http:
        processor = DeliveryProcessor(
            create_session_factory(engine),
            WebhookSender(http, snippet_bytes=settings.response_snippet_bytes),
            Policies.from_settings(settings),
            SystemClock(),
        )
        dispatcher = Dispatcher(
            processor,
            workers=settings.dispatcher_workers,
            idle_poll_seconds=settings.dispatcher_idle_poll_seconds,
            wake_dsn=settings.asyncpg_dsn,
        )
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, dispatcher.stop)
        try:
            await dispatcher.run()
        finally:
            await engine.dispose()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
