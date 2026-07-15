"""Integration fixtures.

Tests run against a real PostgreSQL. By default a disposable ``postgres:16-alpine``
container is started with testcontainers; set ``RELAY_TEST_DATABASE_URL`` to point at an
existing database instead (CI services, or a local server when Docker is unavailable).
The schema is rebuilt from the Alembic migrations once per session.
"""

import asyncio
import os
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from relay.api.app import create_app
from relay.auth.rbac import ROLE_SCOPES, Principal
from relay.config import Settings
from relay.delivery.client import WebhookSender
from relay.dispatcher.processor import DeliveryProcessor, Policies
from relay.dispatcher.runner import Dispatcher
from relay.domain.enums import Role
from relay.domain.models import (
    AppCreateIn,
    EndpointCreateIn,
    EndpointOut,
    EventTypeCreateIn,
    MessageCreatedOut,
    MessageCreateIn,
)
from relay.domain.retry import RetryPolicy
from relay.ids import new_id
from relay.persistence.tables import Attempt, Delivery, Org, User
from relay.services.catalog import AppService, EndpointService, EventTypeService
from relay.services.messages import MessageService
from tests.support import FakeClock

BACKEND_DIR = Path(__file__).resolve().parents[2]
TABLES = (
    "attempts, deliveries, messages, breaker_state, endpoint_secrets, endpoints, "
    "event_types, api_keys, apps, users, orgs"
)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    configured = os.environ.get("RELAY_TEST_DATABASE_URL")
    if configured:
        # The suite drops the public schema, so never let it near a real database.
        name = make_url(configured).database or ""
        if not name.endswith("_test"):
            pytest.exit(f"RELAY_TEST_DATABASE_URL must name a *_test database, got {name!r}")
        yield configured
        return
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def migrated(database_url: str) -> str:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logging"] = False
    _reset_schema(database_url)
    command.upgrade(config, "head")
    return database_url


def _reset_schema(database_url: str) -> None:
    async def run() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(run())


@pytest.fixture(scope="session")
async def engine(migrated: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated, pool_size=20, max_overflow=20)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _clean(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    if "engine" not in request.fixturenames:
        yield
        return
    engine: AsyncEngine = request.getfixturevalue("engine")
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} CASCADE"))
    yield


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings(migrated: str) -> Settings:
    return Settings(
        env="test",
        database_url=migrated,
        log_level="WARNING",
        retry_base_seconds=5,
        retry_max_backoff_seconds=600,
        retry_max_attempts=4,
        breaker_failure_threshold=3,
        breaker_base_cooldown_seconds=30,
        breaker_max_cooldown_seconds=120,
        breaker_disable_after_trips=3,
        breaker_probe_timeout_seconds=10,
    )


@dataclass
class Tenant:
    org_id: str
    owner: Principal
    app_id: str


TenantFactory = Callable[..., Awaitable[Tenant]]
EndpointFactory = Callable[..., Awaitable[EndpointOut]]


@pytest.fixture
def make_tenant(sessions: async_sessionmaker[AsyncSession], clock: FakeClock) -> TenantFactory:
    async def factory(
        name: str = "Acme", event_types: tuple[str, ...] = ("invoice.paid",)
    ) -> Tenant:
        async with sessions() as session:
            org = Org(id=new_id("org"), name=name)
            session.add(org)
            await session.flush()
            user = User(
                id=new_id("usr"),
                org_id=org.id,
                email=f"{org.id}@relay.dev",
                name="Owner",
                password_hash="x",
                role=Role.OWNER.value,
            )
            session.add(user)
            await session.commit()
            principal = Principal(
                kind="user",
                subject_id=user.id,
                org_id=org.id,
                scopes=ROLE_SCOPES[Role.OWNER],
                role=Role.OWNER,
            )
            app = await AppService(session).create(principal, AppCreateIn(name=f"{name} app"))
            for event_type in event_types:
                await EventTypeService(session, clock).create(
                    principal, app.id, EventTypeCreateIn(name=event_type)
                )
            return Tenant(org_id=org.id, owner=principal, app_id=app.id)

    return factory


@pytest.fixture
def make_endpoint(
    sessions: async_sessionmaker[AsyncSession], settings: Settings, clock: FakeClock
) -> EndpointFactory:
    async def factory(tenant: Tenant, **fields: object) -> EndpointOut:
        data = EndpointCreateIn.model_validate({"url": "https://hooks.example.com/relay", **fields})
        async with sessions() as session:
            return await EndpointService(session, settings, clock).create(
                tenant.owner, tenant.app_id, data
            )

    return factory


class Receiver:
    """Scriptable httpx transport standing in for subscriber endpoints."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: list[httpx.Response] = []
        self.default = httpx.Response(200, json={"ok": True})

    def queue(self, *responses: httpx.Response) -> None:
        self.responses.extend(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0) if self.responses else self.default


@pytest.fixture
def receiver() -> Receiver:
    return Receiver()


@pytest.fixture
async def dispatcher(
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    clock: FakeClock,
    receiver: Receiver,
) -> AsyncIterator[Dispatcher]:
    policies = Policies.from_settings(settings)
    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver.handler)) as http:
        processor = DeliveryProcessor(
            sessions,
            WebhookSender(http, snippet_bytes=256),
            policies,
            clock,
            rng=random.Random(42),
        )
        yield Dispatcher(processor, workers=4, idle_poll_seconds=0.05)


@pytest.fixture
def retry_policy(settings: Settings) -> RetryPolicy:
    return Policies.from_settings(settings).retry


@pytest.fixture
async def api(settings: Settings, clock: FakeClock) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, clock)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://relay.test") as client:
            yield client


Publisher = Callable[..., Awaitable[MessageCreatedOut]]


@pytest.fixture
def publish(sessions: async_sessionmaker[AsyncSession], clock: FakeClock) -> Publisher:
    async def factory(
        tenant: Tenant,
        event_type: str = "invoice.paid",
        payload: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> MessageCreatedOut:
        data = MessageCreateIn(event_type=event_type, payload=payload or {"invoice_id": "in_1"})
        async with sessions() as session:
            return await MessageService(session, clock).publish(
                tenant.owner, tenant.app_id, data, idempotency_key=idempotency_key
            )

    return factory


async def fetch_deliveries(
    sessions: async_sessionmaker[AsyncSession], **filters: object
) -> list[Delivery]:
    async with sessions() as session:
        stmt = select(Delivery).filter_by(**filters).order_by(Delivery.id)
        return list((await session.execute(stmt)).scalars())


async def fetch_attempts(
    sessions: async_sessionmaker[AsyncSession], **filters: object
) -> list[Attempt]:
    async with sessions() as session:
        stmt = select(Attempt).filter_by(**filters).order_by(Attempt.id)
        return list((await session.execute(stmt)).scalars())
