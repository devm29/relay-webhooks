from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relay.auth.rbac import Principal
from relay.clock import Clock
from relay.config import Settings
from relay.delivery.client import BlockedAddressError, resolve_public
from relay.domain.errors import ConflictError, NotFoundError, ValidationFailedError
from relay.domain.models import (
    AppCreateIn,
    AppUpdateIn,
    BreakerOut,
    EndpointCreateIn,
    EndpointOut,
    EndpointSecretsOut,
    EndpointUpdateIn,
    EventTypeCreateIn,
    EventTypeUpdateIn,
    RotateSecretIn,
    SecretOut,
)
from relay.ids import new_id
from relay.persistence import queue
from relay.persistence.repositories.catalog import EndpointRepository, EventTypeRepository
from relay.persistence.repositories.tenants import AppRepository
from relay.persistence.tables import App, BreakerStateRow, Endpoint, EndpointSecret, EventType
from relay.services.access import load_app
from relay.services.schemas import ensure_valid_schema
from relay.signing import generate_secret


class AppService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.apps = AppRepository(session)

    async def create(self, principal: Principal, data: AppCreateIn) -> App:
        conflict = ConflictError(f"an app named {data.name!r} already exists")
        if await self.apps.by_name(principal.org_id, data.name):
            raise conflict
        try:
            app = await self.apps.add(
                App(
                    id=new_id("app"),
                    org_id=principal.org_id,
                    name=data.name,
                    description=data.description,
                )
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise conflict from exc
        return app

    async def list_page(
        self, principal: Principal, *, before: str | None, limit: int
    ) -> tuple[list[App], str | None]:
        return await self.apps.list_page(principal.org_id, before=before, limit=limit)

    async def get(self, principal: Principal, app_id: str) -> App:
        return await load_app(self.session, principal, app_id)

    async def update(self, principal: Principal, app_id: str, data: AppUpdateIn) -> App:
        app = await load_app(self.session, principal, app_id)
        changes = data.model_dump(exclude_unset=True)
        if "name" in changes and changes["name"] is None:
            raise ValidationFailedError("name cannot be null")
        for field, value in changes.items():
            setattr(app, field, value)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("an app with this name already exists") from exc
        return app

    async def delete(self, principal: Principal, app_id: str) -> None:
        app = await load_app(self.session, principal, app_id)
        await self.apps.delete(app)
        await self.session.commit()


class EventTypeService:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.session = session
        self.clock = clock
        self.event_types = EventTypeRepository(session)

    async def create(self, principal: Principal, app_id: str, data: EventTypeCreateIn) -> EventType:
        await load_app(self.session, principal, app_id)
        if data.payload_schema is not None:
            ensure_valid_schema(data.payload_schema)
        conflict = ConflictError(f"event type {data.name!r} already exists")
        if await self.event_types.get(app_id, data.name):
            raise conflict
        now = self.clock.now()
        try:
            event_type = await self.event_types.add(
                EventType(
                    id=new_id("evt"),
                    app_id=app_id,
                    name=data.name,
                    description=data.description,
                    payload_schema=data.payload_schema,
                    version=1,
                    archived=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise conflict from exc
        return event_type

    async def list_all(
        self, principal: Principal, app_id: str, *, include_archived: bool
    ) -> list[EventType]:
        await load_app(self.session, principal, app_id)
        return await self.event_types.list_all(app_id, include_archived=include_archived)

    async def get(self, principal: Principal, app_id: str, name: str) -> EventType:
        await load_app(self.session, principal, app_id)
        event_type = await self.event_types.get(app_id, name)
        if event_type is None:
            raise NotFoundError(f"event type {name!r} not found")
        return event_type

    async def update(
        self, principal: Principal, app_id: str, name: str, data: EventTypeUpdateIn
    ) -> EventType:
        event_type = await self.get(principal, app_id, name)
        changes = data.model_dump(exclude_unset=True)
        if "payload_schema" in changes:
            if changes["payload_schema"] is not None:
                ensure_valid_schema(changes["payload_schema"])
            event_type.payload_schema = changes["payload_schema"]
            event_type.version += 1
        if "description" in changes:
            event_type.description = changes["description"]
        if changes.get("archived") is not None:
            event_type.archived = changes["archived"]
        event_type.updated_at = self.clock.now()
        await self.session.commit()
        return event_type

    async def delete(self, principal: Principal, app_id: str, name: str) -> None:
        event_type = await self.get(principal, app_id, name)
        await self.event_types.delete(event_type)
        await self.session.commit()


async def ensure_public_url(url: str) -> None:
    """Early feedback for the operator. The dispatcher re-checks on every connection."""
    host = urlsplit(url).hostname
    if not host:
        raise ValidationFailedError("endpoint url has no host")
    try:
        await resolve_public(host)
    except BlockedAddressError as exc:
        raise ValidationFailedError(
            f"endpoint host {host!r} resolves to a private address; "
            "set RELAY_ALLOW_PRIVATE_ENDPOINTS=true to allow it"
        ) from exc
    except httpx.ConnectError as exc:
        raise ValidationFailedError(f"cannot resolve endpoint host {host!r}") from exc


def endpoint_out(endpoint: Endpoint, breaker: BreakerStateRow | None) -> EndpointOut:
    out = EndpointOut.model_validate(endpoint)
    if breaker is not None:
        out.breaker = BreakerOut.model_validate(breaker)
    return out


class EndpointService:
    def __init__(self, session: AsyncSession, settings: Settings, clock: Clock) -> None:
        self.session = session
        self.settings = settings
        self.clock = clock
        self.endpoints = EndpointRepository(session)

    async def _load(self, principal: Principal, app_id: str, endpoint_id: str) -> Endpoint:
        await load_app(self.session, principal, app_id)
        endpoint = await self.endpoints.get(app_id, endpoint_id)
        if endpoint is None:
            raise NotFoundError(f"endpoint {endpoint_id} not found")
        return endpoint

    async def _check_event_types(self, app_id: str, names: list[str]) -> list[str]:
        wanted = sorted(set(names))
        known = await EventTypeRepository(self.session).existing_names(app_id, wanted)
        unknown = [name for name in wanted if name not in known]
        if unknown:
            raise ValidationFailedError(
                "endpoint subscribes to event types that are not registered",
                details=[
                    {"path": "event_types", "message": f"unknown event type {name!r}"}
                    for name in unknown
                ],
            )
        return wanted

    async def _with_breaker(self, endpoint: Endpoint) -> EndpointOut:
        breakers = await self.endpoints.breakers([endpoint.id])
        return endpoint_out(endpoint, breakers.get(endpoint.id))

    async def create(
        self, principal: Principal, app_id: str, data: EndpointCreateIn
    ) -> EndpointOut:
        await load_app(self.session, principal, app_id)
        url = str(data.url)
        if not self.settings.private_endpoints_allowed:
            await ensure_public_url(url)
        event_types = await self._check_event_types(app_id, data.event_types)
        now = self.clock.now()
        endpoint = Endpoint(
            id=new_id("ep"),
            app_id=app_id,
            name=data.name,
            url=url,
            description=data.description,
            event_types=event_types,
            rate_limit_per_second=data.rate_limit_per_second,
            timeout_seconds=data.timeout_seconds,
            headers=data.headers,
            disabled=data.disabled,
            created_at=now,
            updated_at=now,
        )
        secret = EndpointSecret(
            id=new_id("whs"),
            endpoint_id=endpoint.id,
            secret=data.secret or generate_secret(),
            created_at=now,
        )
        await self.endpoints.add(endpoint, secret)
        await self.session.commit()
        return await self._with_breaker(endpoint)

    async def list_page(
        self, principal: Principal, app_id: str, *, before: str | None, limit: int
    ) -> tuple[list[EndpointOut], str | None]:
        await load_app(self.session, principal, app_id)
        rows, cursor = await self.endpoints.list_page(app_id, before=before, limit=limit)
        breakers = await self.endpoints.breakers([e.id for e in rows])
        return [endpoint_out(e, breakers.get(e.id)) for e in rows], cursor

    async def get(self, principal: Principal, app_id: str, endpoint_id: str) -> EndpointOut:
        return await self._with_breaker(await self._load(principal, app_id, endpoint_id))

    async def update(
        self, principal: Principal, app_id: str, endpoint_id: str, data: EndpointUpdateIn
    ) -> EndpointOut:
        endpoint = await self._load(principal, app_id, endpoint_id)
        changes = data.model_dump(exclude_unset=True)
        now = self.clock.now()
        if "url" in changes:
            if data.url is None:
                raise ValidationFailedError("url cannot be null")
            endpoint.url = str(data.url)
            if not self.settings.private_endpoints_allowed:
                await ensure_public_url(endpoint.url)
        if "event_types" in changes:
            endpoint.event_types = await self._check_event_types(app_id, data.event_types or [])
        if "headers" in changes:
            endpoint.headers = data.headers or {}
        for field in ("name", "description", "rate_limit_per_second", "timeout_seconds"):
            if field in changes:
                setattr(endpoint, field, changes[field])
        if data.disabled is True and not endpoint.disabled:
            endpoint.disabled = True
            endpoint.disabled_reason = "disabled manually"
        elif data.disabled is False and endpoint.disabled:
            await self._reenable(endpoint)
        endpoint.updated_at = now
        await self.session.commit()
        return await self._with_breaker(endpoint)

    async def _reenable(self, endpoint: Endpoint) -> None:
        now = self.clock.now()
        endpoint.disabled = False
        endpoint.disabled_reason = None
        endpoint.updated_at = now
        await self.endpoints.reset_breaker(endpoint.id, now)
        await queue.resume_endpoint(self.session, endpoint.id, now)

    async def enable(self, principal: Principal, app_id: str, endpoint_id: str) -> EndpointOut:
        """Re-enable and close the breaker: the operator's way of saying the receiver is fixed."""
        endpoint = await self._load(principal, app_id, endpoint_id)
        await self._reenable(endpoint)
        await self.session.commit()
        return await self._with_breaker(endpoint)

    async def delete(self, principal: Principal, app_id: str, endpoint_id: str) -> None:
        """Soft delete: the endpoint stops receiving traffic and disappears from the console,
        but its deliveries and attempts stay in the audit trail."""
        endpoint = await self._load(principal, app_id, endpoint_id)
        now = self.clock.now()
        await self.endpoints.soft_delete(endpoint, now)
        await queue.bury_endpoint(self.session, endpoint.id, now)
        await self.session.commit()

    async def secrets(
        self, principal: Principal, app_id: str, endpoint_id: str
    ) -> EndpointSecretsOut:
        await self._load(principal, app_id, endpoint_id)
        active = await self.endpoints.active_secrets(endpoint_id, self.clock.now())
        current = next((s for s in active if s.expires_at is None), None)
        if current is None:
            raise NotFoundError("endpoint has no active signing secret")
        return EndpointSecretsOut(
            current=SecretOut.model_validate(current),
            previous=[SecretOut.model_validate(s) for s in active if s is not current],
        )

    async def rotate_secret(
        self, principal: Principal, app_id: str, endpoint_id: str, data: RotateSecretIn
    ) -> EndpointSecretsOut:
        await self._load(principal, app_id, endpoint_id)
        now = self.clock.now()
        overlap = (
            data.overlap_seconds
            if data.overlap_seconds is not None
            else self.settings.secret_rotation_overlap_seconds
        )
        await self.endpoints.rotate_secret(
            endpoint_id,
            EndpointSecret(
                id=new_id("whs"),
                endpoint_id=endpoint_id,
                secret=data.secret or generate_secret(),
                created_at=now,
            ),
            retire_at=now + timedelta(seconds=overlap),
        )
        await self.session.commit()
        return await self.secrets(principal, app_id, endpoint_id)
