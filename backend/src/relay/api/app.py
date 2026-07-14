from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from relay.api.errors import ErrorResponse, install_error_handlers
from relay.api.middleware import RequestContextMiddleware
from relay.api.routes import (
    apps,
    auth,
    deliveries,
    endpoints,
    event_types,
    health,
    messages,
    stream,
)
from relay.auth.throttle import LoginThrottle
from relay.chaos.app import create_chaos_app
from relay.clock import Clock, SystemClock
from relay.config import Settings, get_settings
from relay.events.hub import LiveHub, live_listener
from relay.logging import configure_logging, get_logger
from relay.persistence.db import create_engine, create_session_factory

log = get_logger(__name__)


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        hub = LiveHub()
        listener = live_listener(settings.asyncpg_dsn, hub)
        app.state.settings = settings
        app.state.clock = clock or SystemClock()
        app.state.sessions = create_session_factory(engine)
        app.state.hub = hub
        app.state.login_throttle = LoginThrottle(
            per_account=settings.login_attempts_per_minute,
            per_client=settings.login_attempts_per_minute_per_client,
        )
        await listener.start()
        try:
            yield
        finally:
            await listener.stop()
            await engine.dispose()

    app = FastAPI(
        title="Relay",
        version="0.1.0",
        summary="Multi-tenant outbound webhooks on Postgres",
        lifespan=lifespan,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["idempotent-replayed", "x-request-id"],
    )
    install_error_handlers(app)

    v1 = APIRouter(prefix="/api/v1")
    for module in (auth, apps, event_types, endpoints, messages, deliveries, stream):
        v1.include_router(module.router)
    app.include_router(v1)
    app.include_router(health.router)

    if settings.chaos_mount:
        log.warning("chaos.mounted", path="/chaos", note="unauthenticated demo routes are exposed")
        app.mount("/chaos", create_chaos_app(settings.chaos_verify_secret))

    return app
