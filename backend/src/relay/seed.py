"""Demo data: a tenant with realistic endpoints, a day of delivery history, and an
optional traffic generator that keeps the live log moving.

    relay-seed                 # reset + seed
    relay-seed traffic --rate 3
"""

import argparse
import asyncio
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from relay.auth.api_keys import generate_api_key
from relay.auth.passwords import hash_password
from relay.auth.rbac import ROLE_SCOPES, Principal
from relay.clock import SystemClock
from relay.config import Settings, get_settings
from relay.domain.breaker import BreakerPolicy, BreakerSnapshot, cooldown
from relay.domain.enums import BreakerState, Role, Scope
from relay.domain.models import MessageCreateIn
from relay.domain.retry import RetryPolicy, backoff_delay
from relay.ids import new_id
from relay.logging import configure_logging, get_logger
from relay.persistence.db import create_engine, create_session_factory
from relay.persistence.tables import (
    ApiKey,
    App,
    Attempt,
    BreakerStateRow,
    Delivery,
    Endpoint,
    EndpointSecret,
    EventType,
    Message,
    Org,
    User,
)
from relay.services.messages import MessageService, request_fingerprint

log = get_logger("relay.seed")

DEMO_EMAIL = "demo@relay.dev"
DEMO_PASSWORD = "relay-demo-password"
DEMO_SECRET = "whsec_cmVsYXktZGVtby1zaWduaW5nLXNlY3JldC0wMQ=="
ORG_NAME = "Northwind Labs"
APP_NAME = "Northwind Commerce"

_TABLES = (
    "attempts, deliveries, messages, breaker_state, endpoint_secrets, endpoints, "
    "event_types, api_keys, apps, users, orgs"
)

_MONEY = {"type": "integer", "minimum": 0}
_ID = {"type": "string", "minLength": 3}

EVENT_TYPES: dict[str, tuple[str, dict[str, Any]]] = {
    "invoice.paid": (
        "An invoice was paid in full.",
        {
            "type": "object",
            "required": ["invoice_id", "customer_id", "amount", "currency"],
            "properties": {
                "invoice_id": _ID,
                "customer_id": _ID,
                "amount": _MONEY,
                "currency": {"type": "string", "enum": ["usd", "eur", "gbp"]},
            },
        },
    ),
    "invoice.payment_failed": (
        "A payment attempt for an invoice was declined.",
        {
            "type": "object",
            "required": ["invoice_id", "customer_id", "decline_code"],
            "properties": {
                "invoice_id": _ID,
                "customer_id": _ID,
                "decline_code": {"type": "string"},
            },
        },
    ),
    "customer.created": (
        "A new customer signed up.",
        {
            "type": "object",
            "required": ["customer_id", "email"],
            "properties": {
                "customer_id": _ID,
                "email": {"type": "string"},
                "plan": {"type": "string", "enum": ["starter", "team", "business"]},
            },
        },
    ),
    "subscription.renewed": (
        "A subscription renewed for another billing period.",
        {
            "type": "object",
            "required": ["subscription_id", "customer_id", "period_end"],
            "properties": {
                "subscription_id": _ID,
                "customer_id": _ID,
                "period_end": {"type": "string"},
            },
        },
    ),
    "subscription.canceled": (
        "A customer canceled their subscription.",
        {
            "type": "object",
            "required": ["subscription_id", "customer_id", "reason"],
            "properties": {
                "subscription_id": _ID,
                "customer_id": _ID,
                "reason": {"type": "string"},
            },
        },
    ),
    "order.shipped": (
        "An order left the warehouse.",
        {
            "type": "object",
            "required": ["order_id", "carrier", "tracking_number"],
            "properties": {
                "order_id": _ID,
                "carrier": {"type": "string"},
                "tracking_number": {"type": "string"},
            },
        },
    ),
    "refund.issued": (
        "A refund was issued to a customer.",
        {
            "type": "object",
            "required": ["refund_id", "invoice_id", "amount"],
            "properties": {"refund_id": _ID, "invoice_id": _ID, "amount": _MONEY},
        },
    ),
}

EVENT_WEIGHTS = {
    "invoice.paid": 30,
    "customer.created": 18,
    "order.shipped": 16,
    "subscription.renewed": 14,
    "invoice.payment_failed": 8,
    "refund.issued": 6,
    "subscription.canceled": 4,
}


@dataclass(frozen=True)
class Profile:
    slug: str
    name: str
    description: str
    chaos: dict[str, str | int | float]
    event_types: tuple[str, ...] = ()
    latency_ms: tuple[int, int] = (40, 120)
    fail_rate: float = 0.0
    fail_status: int = 500
    timeout_rate: float = 0.0
    rate_limit: float | None = None
    timeout_seconds: float | None = None
    outage_last_hours: float | None = None
    disabled_reason: str | None = None


PROFILES = (
    Profile(
        "ledger",
        "Ledger service",
        "Books revenue the moment money moves",
        {"latency_ms": 35, "jitter_ms": 50},
        event_types=("invoice.paid", "refund.issued", "invoice.payment_failed"),
        latency_ms=(30, 90),
    ),
    Profile(
        "crm-sync",
        "CRM sync",
        "Keeps customer records in Salesforce current",
        {"latency_ms": 110, "jitter_ms": 180, "fail_rate": 0.04},
        event_types=("customer.created", "subscription.renewed", "subscription.canceled"),
        latency_ms=(100, 320),
        fail_rate=0.04,
    ),
    Profile(
        "fulfillment",
        "Fulfillment",
        "Prints labels and notifies the warehouse",
        {"latency_ms": 260, "jitter_ms": 420, "timeout_rate": 0.02},
        event_types=("order.shipped", "invoice.paid"),
        latency_ms=(240, 900),
        timeout_rate=0.02,
        rate_limit=5,
        timeout_seconds=10,
    ),
    Profile(
        "analytics",
        "Analytics warehouse",
        "Sheds load with 503 + Retry-After",
        {
            "latency_ms": 80,
            "jitter_ms": 120,
            "fail_rate": 0.3,
            "fail_status": 503,
            "retry_after": 20,
        },
        latency_ms=(70, 260),
        fail_rate=0.3,
        fail_status=503,
    ),
    Profile(
        "legacy-erp",
        "Legacy ERP bridge",
        "Currently down for a database migration",
        {"latency_ms": 900, "jitter_ms": 600, "fail_rate": 1, "fail_status": 502},
        event_types=("invoice.paid", "refund.issued"),
        latency_ms=(700, 1600),
        fail_rate=0.06,
        fail_status=502,
        outage_last_hours=1.5,
    ),
    Profile(
        "partner-acme",
        "Acme partner integration",
        "Decommissioned on their side",
        {"gone": "true"},
        event_types=("order.shipped",),
        latency_ms=(120, 240),
        disabled_reason="endpoint responded 410 Gone",
        outage_last_hours=20,
    ),
)

FIRST_NAMES = ["ava", "liam", "mia", "noah", "zoe", "ethan", "isla", "leo", "sofia", "kai"]
COMPANIES = ["fabrikam", "contoso", "tailspin", "wingtip", "litware", "adventureworks"]
CARRIERS = ["UPS", "FedEx", "DHL", "USPS"]


def _ref(rng: random.Random, prefix: str) -> str:
    return f"{prefix}_{rng.randrange(16**10):010x}"


def fake_payload(event_type: str, rng: random.Random) -> dict[str, Any]:
    customer = _ref(rng, "cus")
    match event_type:
        case "invoice.paid":
            return {
                "invoice_id": _ref(rng, "in"),
                "customer_id": customer,
                "amount": rng.choice([1900, 4900, 9900, 24900, 129900]),
                "currency": rng.choice(["usd", "usd", "usd", "eur", "gbp"]),
            }
        case "invoice.payment_failed":
            return {
                "invoice_id": _ref(rng, "in"),
                "customer_id": customer,
                "decline_code": rng.choice(["insufficient_funds", "expired_card", "do_not_honor"]),
            }
        case "customer.created":
            name = rng.choice(FIRST_NAMES)
            return {
                "customer_id": customer,
                "email": f"{name}@{rng.choice(COMPANIES)}.com",
                "plan": rng.choice(["starter", "team", "business"]),
            }
        case "subscription.renewed":
            return {
                "subscription_id": _ref(rng, "sub"),
                "customer_id": customer,
                "period_end": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
            }
        case "subscription.canceled":
            return {
                "subscription_id": _ref(rng, "sub"),
                "customer_id": customer,
                "reason": rng.choice(["too_expensive", "switched_provider", "missing_feature"]),
            }
        case "order.shipped":
            return {
                "order_id": _ref(rng, "ord"),
                "carrier": rng.choice(CARRIERS),
                "tracking_number": f"1Z{rng.randrange(10**12):012d}",
            }
        case _:
            return {
                "refund_id": _ref(rng, "re"),
                "invoice_id": _ref(rng, "in"),
                "amount": rng.choice([900, 1900, 4900]),
            }


def pick_event_type(rng: random.Random) -> str:
    names = list(EVENT_WEIGHTS)
    return rng.choices(names, weights=[EVENT_WEIGHTS[n] for n in names])[0]


def endpoint_url(base: str, profile: Profile) -> str:
    return f"{base.rstrip('/')}/hooks/{profile.slug}?{urlencode(profile.chaos)}"


async def reset(session: AsyncSession) -> None:
    await session.execute(text(f"TRUNCATE {_TABLES} CASCADE"))


class HistoryBuilder:
    """Synthesises a day of delivery history so dashboards have shape on first load."""

    def __init__(self, rng: random.Random, now: datetime, settings: Settings) -> None:
        self.rng = rng
        self.now = now
        self.retry = RetryPolicy(
            base_seconds=settings.retry_base_seconds,
            max_backoff_seconds=settings.retry_max_backoff_seconds,
            max_attempts=settings.retry_max_attempts,
        )
        self.messages: list[dict[str, Any]] = []
        self.deliveries: list[dict[str, Any]] = []
        self.attempts: list[dict[str, Any]] = []
        self.gone: set[str] = set()

    def _in_outage(self, profile: Profile, at: datetime) -> bool:
        if profile.outage_last_hours is None:
            return False
        return at >= self.now - timedelta(hours=profile.outage_last_hours)

    def _attempt_outcome(
        self, profile: Profile, at: datetime
    ) -> tuple[int | None, str | None, int]:
        low, high = profile.latency_ms
        latency = int(self.rng.triangular(low, high, low + (high - low) * 0.3))
        if profile.disabled_reason and self._in_outage(profile, at):
            return 410, "endpoint responded 410 Gone", latency
        if self._in_outage(profile, at):
            return profile.fail_status, f"HTTP {profile.fail_status}", latency
        roll = self.rng.random()
        if roll < profile.timeout_rate:
            timeout = profile.timeout_seconds or 15
            return None, f"timed out after {timeout:g}s", int(timeout * 1000)
        if roll < profile.timeout_rate + profile.fail_rate:
            return profile.fail_status, f"HTTP {profile.fail_status}", latency
        return 200, None, latency

    def add(
        self, app_id: str, endpoints: list[tuple[str, Profile]], at: datetime, event_type: str
    ) -> None:
        payload = fake_payload(event_type, self.rng)
        ms = int(at.timestamp() * 1000)
        message_id = new_id("msg", now_ms=ms)
        self.messages.append(
            {
                "id": message_id,
                "app_id": app_id,
                "event_type": event_type,
                "event_id": None,
                "idempotency_key": None,
                "request_fingerprint": request_fingerprint(
                    MessageCreateIn(event_type=event_type, payload=payload)
                ),
                "payload": payload,
                "created_at": at,
            }
        )
        for endpoint_id, profile in endpoints:
            if profile.event_types and event_type not in profile.event_types:
                continue
            if profile.disabled_reason and self._in_outage(profile, at):
                # The first 410 disables the endpoint; later messages never fan out to it.
                if endpoint_id in self.gone:
                    continue
                self.gone.add(endpoint_id)
            self._deliver(app_id, message_id, endpoint_id, profile, at)

    def _deliver(
        self, app_id: str, message_id: str, endpoint_id: str, profile: Profile, created: datetime
    ) -> None:
        delivery_id = new_id("dlv", now_ms=int(created.timestamp() * 1000))
        at = created + timedelta(milliseconds=self.rng.randint(5, 60))
        status, delivered_at, next_at = "pending", None, None
        code: int | None = None
        error: str | None = None
        number = 0
        while True:
            number += 1
            code, error, latency = self._attempt_outcome(profile, at)
            ok = code is not None and 200 <= code < 300
            if ok:
                status, delivered_at, next_at = (
                    "succeeded",
                    at + timedelta(milliseconds=latency),
                    None,
                )
            elif code == 410 or number >= self.retry.max_attempts:
                status, next_at = "dead", None
            else:
                delay = backoff_delay(self.retry, number, rng=self.rng)
                next_at = at + timedelta(milliseconds=latency, seconds=delay)
            self.attempts.append(
                {
                    "id": new_id("atm", now_ms=int(at.timestamp() * 1000)),
                    "app_id": app_id,
                    "delivery_id": delivery_id,
                    "message_id": message_id,
                    "endpoint_id": endpoint_id,
                    "attempt_number": number,
                    "trigger": "scheduled",
                    "outcome": "succeeded" if ok else "failed",
                    "status_code": code,
                    "error": error,
                    "response_snippet": '{"ok":true}'
                    if ok
                    else (f'{{"error":"chaos says {code}"}}' if code else None),
                    "latency_ms": latency,
                    "started_at": at,
                    "next_attempt_at": next_at,
                }
            )
            if next_at is None or next_at > self.now:
                break
            at = next_at

        self.deliveries.append(
            {
                "id": delivery_id,
                "app_id": app_id,
                "message_id": message_id,
                "endpoint_id": endpoint_id,
                "status": status,
                "attempt_count": number,
                "schedule_index": number,
                "next_attempt_at": next_at,
                "last_status_code": code,
                "last_error": error,
                "delivered_at": delivered_at,
                "created_at": created,
                "updated_at": at,
            }
        )


async def seed(
    sessions: async_sessionmaker[AsyncSession], settings: Settings, chaos_url: str
) -> None:
    rng = random.Random(20260301)
    now = datetime.now(UTC)
    secret = settings.chaos_verify_secret or DEMO_SECRET

    async with sessions() as session, session.begin():
        await reset(session)
        org = Org(id=new_id("org"), name=ORG_NAME)
        session.add(org)
        await session.flush()
        people = [
            (DEMO_EMAIL, "Dana Whitfield", Role.OWNER),
            ("marcus@relay.dev", "Marcus Chen", Role.ADMIN),
            ("priya@relay.dev", "Priya Raman", Role.DEVELOPER),
            ("sam@relay.dev", "Sam Okafor", Role.VIEWER),
        ]
        password_hash = hash_password(DEMO_PASSWORD)
        users = [
            User(
                id=new_id("usr"),
                org_id=org.id,
                email=email,
                name=name,
                password_hash=password_hash,
                role=role.value,
            )
            for email, name, role in people
        ]
        session.add_all(users)
        await session.flush()

        # Apps list newest first and the console opens the first one, so the storefront
        # app gets the later id.
        created_ms = int(datetime.now(UTC).timestamp() * 1000)
        app = App(
            id=new_id("app", now_ms=created_ms),
            org_id=org.id,
            name=APP_NAME,
            description="Billing, customer and fulfilment events for the storefront.",
        )
        internal = App(
            id=new_id("app", now_ms=created_ms - 1),
            org_id=org.id,
            name="Northwind Internal",
            description="Back-office notifications.",
        )
        session.add_all([app, internal])
        await session.flush()

        for name, (description, schema) in EVENT_TYPES.items():
            session.add(
                EventType(
                    id=new_id("evt"),
                    app_id=app.id,
                    name=name,
                    description=description,
                    payload_schema=schema,
                    version=1,
                    archived=False,
                )
            )

        endpoints: list[tuple[str, Profile]] = []
        for index, profile in enumerate(PROFILES):
            created = now - timedelta(days=21 - index * 2)
            endpoint = Endpoint(
                id=new_id("ep", now_ms=int(created.timestamp() * 1000)),
                app_id=app.id,
                name=profile.name,
                url=endpoint_url(chaos_url, profile),
                description=profile.description,
                event_types=list(profile.event_types),
                rate_limit_per_second=profile.rate_limit,
                timeout_seconds=profile.timeout_seconds,
                headers={"x-relay-tenant": "northwind"},
                disabled=profile.disabled_reason is not None,
                disabled_reason=profile.disabled_reason,
                created_at=created,
                updated_at=created,
            )
            session.add(endpoint)
            await session.flush()
            session.add(
                EndpointSecret(
                    id=new_id("whs"), endpoint_id=endpoint.id, secret=secret, created_at=created
                )
            )
            endpoints.append((endpoint.id, profile))

        generated = generate_api_key(settings.api_key_pepper.get_secret_value())
        session.add(
            ApiKey(
                id=new_id("key"),
                org_id=org.id,
                name="Storefront backend (production)",
                prefix=generated.prefix,
                key_hash=generated.key_hash,
                scopes=[Scope.MESSAGES_WRITE.value, Scope.MESSAGES_READ.value],
                created_by=users[0].id,
                last_used_at=now - timedelta(minutes=2),
            )
        )

        history = HistoryBuilder(rng, now, settings)
        span = timedelta(hours=24)
        # Skewed towards recent hours so the 24h chart has a shape rather than a flat line.
        moments = sorted(now - span + span * rng.betavariate(2.2, 1.4) for _ in range(4000))
        for at in moments:
            history.add(app.id, endpoints, at, pick_event_type(rng))

        await session.execute(insert(Message), history.messages)
        await session.execute(insert(Delivery), history.deliveries)
        await session.execute(insert(Attempt), history.attempts)

        policy = BreakerPolicy(
            failure_threshold=settings.breaker_failure_threshold,
            base_cooldown_seconds=settings.breaker_base_cooldown_seconds,
            max_cooldown_seconds=settings.breaker_max_cooldown_seconds,
        )
        for endpoint_id, profile in endpoints:
            snapshot = BreakerSnapshot()
            if profile.outage_last_hours is not None and profile.disabled_reason is None:
                trips = 3
                snapshot = BreakerSnapshot(
                    state=BreakerState.OPEN,
                    consecutive_failures=policy.failure_threshold * trips,
                    trip_count=trips,
                    opened_at=now - timedelta(minutes=1),
                    open_until=now + cooldown(policy, trips),
                )
            elif profile.disabled_reason is not None:
                snapshot = BreakerSnapshot(
                    state=BreakerState.OPEN,
                    consecutive_failures=40,
                    trip_count=settings.breaker_disable_after_trips,
                    opened_at=now - timedelta(hours=6),
                    open_until=now - timedelta(hours=5),
                )
            session.add(
                BreakerStateRow(
                    endpoint_id=endpoint_id,
                    state=snapshot.state.value,
                    consecutive_failures=snapshot.consecutive_failures,
                    trip_count=snapshot.trip_count,
                    opened_at=snapshot.opened_at,
                    open_until=snapshot.open_until,
                    updated_at=now,
                )
            )

    log.info(
        "seed.done",
        org=ORG_NAME,
        login=DEMO_EMAIL,
        password=DEMO_PASSWORD,
        api_key=generated.plaintext,
        messages=len(history.messages),
        deliveries=len(history.deliveries),
        attempts=len(history.attempts),
    )


async def traffic(
    sessions: async_sessionmaker[AsyncSession], rate: float, duration: float | None
) -> None:
    rng = random.Random()
    clock = SystemClock()
    async with sessions() as session:
        row = (
            await session.execute(
                text(
                    "SELECT a.id, a.org_id, u.id FROM apps a JOIN users u ON u.org_id = a.org_id "
                    "WHERE a.name = :name AND u.email = :email"
                ),
                {"name": APP_NAME, "email": DEMO_EMAIL},
            )
        ).one_or_none()
    if row is None:
        raise SystemExit("demo tenant not found; run `relay-seed` first")
    app_id, org_id, user_id = row
    principal = Principal(
        kind="user",
        subject_id=user_id,
        org_id=org_id,
        scopes=ROLE_SCOPES[Role.OWNER],
        role=Role.OWNER,
    )
    started = clock.now()
    sent = 0
    log.info("traffic.start", rate=rate)
    while duration is None or (clock.now() - started).total_seconds() < duration:
        event_type = pick_event_type(rng)
        async with sessions() as session:
            await MessageService(session, clock).publish(
                principal,
                app_id,
                MessageCreateIn(event_type=event_type, payload=fake_payload(event_type, rng)),
                idempotency_key=None,
            )
        sent += 1
        await asyncio.sleep(rng.expovariate(rate))
    log.info("traffic.done", sent=sent)


async def _main(args: argparse.Namespace) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.log_json)
    if args.command == "seed" and settings.env == "production" and not args.force:
        raise SystemExit(
            "refusing to seed: RELAY_ENV=production and seeding truncates every table. "
            "Pass --force if you really mean it."
        )
    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    try:
        if args.command == "traffic":
            await traffic(sessions, args.rate, args.duration)
        else:
            await seed(sessions, settings, args.chaos_url)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="relay-seed")
    parser.add_argument("command", nargs="?", choices=["seed", "traffic"], default="seed")
    parser.add_argument(
        "--chaos-url",
        default="http://127.0.0.1:8108/chaos",
        help="base URL of the chaos receiver the demo endpoints point at",
    )
    parser.add_argument("--rate", type=float, default=0.3, help="messages per second (traffic)")
    parser.add_argument("--duration", type=float, default=None, help="seconds to run (traffic)")
    parser.add_argument(
        "--force", action="store_true", help="allow seeding when RELAY_ENV=production"
    )
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
