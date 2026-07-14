import hashlib
import json

from sqlalchemy.ext.asyncio import AsyncSession

from relay.auth.rbac import Principal
from relay.clock import Clock
from relay.domain.enums import AttemptOutcome, AttemptTrigger, DeliveryStatus
from relay.domain.errors import ConflictError, NotFoundError, ValidationFailedError
from relay.domain.models import (
    AttemptLogOut,
    AttemptOut,
    BulkReplayIn,
    DeliveryDetailOut,
    DeliveryOut,
    LiveEvent,
    MessageCreatedOut,
    MessageCreateIn,
    MessageDetailOut,
    MessageOut,
)
from relay.events.notify import publish_live, wake_dispatchers
from relay.persistence import outbox, queue
from relay.persistence.repositories.activity import (
    AttemptRepository,
    AttemptView,
    DeliveryRepository,
    DeliveryView,
    MessageRepository,
)
from relay.persistence.repositories.catalog import EndpointRepository, EventTypeRepository
from relay.persistence.tables import Attempt
from relay.services.access import load_app
from relay.services.schemas import validate_payload_async


def delivery_out(view: DeliveryView) -> DeliveryOut:
    d = view.delivery
    return DeliveryOut(
        id=d.id,
        app_id=d.app_id,
        message_id=d.message_id,
        endpoint_id=d.endpoint_id,
        status=DeliveryStatus(d.status),
        attempt_count=d.attempt_count,
        next_attempt_at=d.next_attempt_at,
        last_status_code=d.last_status_code,
        last_error=d.last_error,
        delivered_at=d.delivered_at,
        created_at=d.created_at,
        updated_at=d.updated_at,
        event_type=view.event_type,
        endpoint_url=view.endpoint_url,
    )


def attempt_out(a: Attempt) -> AttemptOut:
    return AttemptOut(
        id=a.id,
        delivery_id=a.delivery_id,
        message_id=a.message_id,
        endpoint_id=a.endpoint_id,
        attempt_number=a.attempt_number,
        trigger=AttemptTrigger(a.trigger),
        outcome=AttemptOutcome(a.outcome),
        status_code=a.status_code,
        error=a.error,
        response_snippet=a.response_snippet,
        latency_ms=a.latency_ms,
        started_at=a.started_at,
        next_attempt_at=a.next_attempt_at,
    )


def attempt_log_out(view: AttemptView) -> AttemptLogOut:
    return AttemptLogOut(
        **attempt_out(view.attempt).model_dump(),
        event_type=view.event_type,
        endpoint_url=view.endpoint_url,
        delivery_status=DeliveryStatus(view.delivery_status),
    )


def request_fingerprint(data: MessageCreateIn) -> str:
    canonical = json.dumps(
        {"event_type": data.event_type, "event_id": data.event_id, "payload": data.payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class MessageService:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.session = session
        self.clock = clock
        self.messages = MessageRepository(session)
        self.deliveries = DeliveryRepository(session)

    async def publish(
        self,
        principal: Principal,
        app_id: str,
        data: MessageCreateIn,
        *,
        idempotency_key: str | None,
    ) -> MessageCreatedOut:
        await load_app(self.session, principal, app_id)
        event_type = await EventTypeRepository(self.session).get(app_id, data.event_type)
        if event_type is None:
            raise ValidationFailedError(
                f"unknown event type {data.event_type!r}; register it before publishing"
            )
        if event_type.archived:
            raise ValidationFailedError(f"event type {data.event_type!r} is archived")
        if event_type.payload_schema is not None:
            await validate_payload_async(
                event_type.id, event_type.version, event_type.payload_schema, data.payload
            )

        fingerprint = request_fingerprint(data)
        now = self.clock.now()
        result = await outbox.write_message(
            self.session,
            app_id=app_id,
            event_type=data.event_type,
            event_id=data.event_id,
            payload=data.payload,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            now=now,
        )
        if not result.created:
            if result.message.request_fingerprint != fingerprint:
                raise ConflictError(
                    "Idempotency-Key was already used with a different request body"
                )
            return MessageCreatedOut.model_validate(
                {
                    **MessageOut.model_validate(result.message).model_dump(),
                    "fanout": result.fanout,
                    "idempotent_replay": True,
                }
            )

        await publish_live(
            self.session,
            LiveEvent(
                kind="message",
                app_id=app_id,
                id=result.message.id,
                message_id=result.message.id,
                event_type=data.event_type,
                at=now,
            ),
        )
        if result.fanout:
            await wake_dispatchers(self.session)
        await self.session.commit()
        return MessageCreatedOut.model_validate(
            {**MessageOut.model_validate(result.message).model_dump(), "fanout": result.fanout}
        )

    async def list_page(
        self,
        principal: Principal,
        app_id: str,
        *,
        event_type: str | None,
        before: str | None,
        limit: int,
    ) -> tuple[list[MessageOut], str | None]:
        await load_app(self.session, principal, app_id)
        rows, cursor = await self.messages.list_page(
            app_id, event_type=event_type, before=before, limit=limit
        )
        return [MessageOut.model_validate(m) for m in rows], cursor

    async def get(self, principal: Principal, app_id: str, message_id: str) -> MessageDetailOut:
        await load_app(self.session, principal, app_id)
        message = await self.messages.get(app_id, message_id)
        if message is None:
            raise NotFoundError(f"message {message_id} not found")
        deliveries = await self.deliveries.for_message(message.id)
        return MessageDetailOut.model_validate(
            {
                **MessageOut.model_validate(message).model_dump(),
                "deliveries": [delivery_out(d) for d in deliveries],
            }
        )


class DeliveryService:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.session = session
        self.clock = clock
        self.deliveries = DeliveryRepository(session)
        self.attempts = AttemptRepository(session)

    async def list_page(
        self,
        principal: Principal,
        app_id: str,
        *,
        status: DeliveryStatus | None,
        endpoint_id: str | None,
        before: str | None,
        limit: int,
    ) -> tuple[list[DeliveryOut], str | None]:
        await load_app(self.session, principal, app_id)
        rows, cursor = await self.deliveries.list_page(
            app_id, status=status, endpoint_id=endpoint_id, before=before, limit=limit
        )
        return [delivery_out(d) for d in rows], cursor

    async def get(self, principal: Principal, app_id: str, delivery_id: str) -> DeliveryDetailOut:
        await load_app(self.session, principal, app_id)
        view = await self.deliveries.get(app_id, delivery_id)
        if view is None:
            raise NotFoundError(f"delivery {delivery_id} not found")
        message = await MessageRepository(self.session).get(app_id, view.delivery.message_id)
        attempts = await self.attempts.for_delivery(delivery_id)
        return DeliveryDetailOut(
            **delivery_out(view).model_dump(),
            payload=message.payload if message else {},
            attempts=[attempt_out(a) for a in attempts],
        )

    async def replay(self, principal: Principal, app_id: str, delivery_id: str) -> DeliveryOut:
        await load_app(self.session, principal, app_id)
        current = await self.deliveries.get(app_id, delivery_id)
        if current is None:
            raise NotFoundError(f"delivery {delivery_id} not found")
        if await EndpointRepository(self.session).get(app_id, current.delivery.endpoint_id) is None:
            raise ConflictError("the endpoint for this delivery was deleted; it cannot be replayed")
        if not await queue.replay_one(self.session, app_id, delivery_id, self.clock.now()):
            raise ConflictError("delivery is being attempted right now; try again in a moment")
        await wake_dispatchers(self.session)
        await self.session.commit()
        self.session.expire_all()
        view = await self.deliveries.get(app_id, delivery_id)
        assert view is not None
        return delivery_out(view)

    async def replay_bulk(self, principal: Principal, app_id: str, data: BulkReplayIn) -> int:
        await load_app(self.session, principal, app_id)
        endpoints = EndpointRepository(self.session)
        if data.endpoint_id is not None and await endpoints.get(app_id, data.endpoint_id) is None:
            raise NotFoundError(f"endpoint {data.endpoint_id} not found")
        count = await queue.replay_many(
            self.session,
            app_id,
            status=DeliveryStatus(data.status),
            endpoint_id=data.endpoint_id,
            since=data.since,
            until=data.until,
            now=self.clock.now(),
        )
        if count:
            await wake_dispatchers(self.session)
        await self.session.commit()
        return count

    async def attempt_log(
        self,
        principal: Principal,
        app_id: str,
        *,
        endpoint_id: str | None,
        before: str | None,
        limit: int,
    ) -> tuple[list[AttemptLogOut], str | None]:
        await load_app(self.session, principal, app_id)
        rows, cursor = await self.attempts.log(
            app_id, endpoint_id=endpoint_id, before=before, limit=limit
        )
        return [attempt_log_out(a) for a in rows], cursor
