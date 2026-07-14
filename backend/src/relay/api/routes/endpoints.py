from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from relay.api.deps import ClockDep, PageDep, Requires, SessionDep, SettingsDep
from relay.auth.rbac import Principal
from relay.domain.enums import Scope
from relay.domain.models import (
    BulkReplayIn,
    EndpointCreateIn,
    EndpointOut,
    EndpointSecretsOut,
    EndpointUpdateIn,
    LatencyStats,
    Page,
    ReplayResultOut,
    RotateSecretIn,
    StatsWindow,
)
from relay.services.catalog import EndpointService
from relay.services.messages import DeliveryService
from relay.services.stats import StatsService

router = APIRouter(prefix="/apps/{app_id}/endpoints", tags=["endpoints"])

Reader = Annotated[Principal, Requires(Scope.ENDPOINTS_READ)]
Writer = Annotated[Principal, Requires(Scope.ENDPOINTS_WRITE)]
Replayer = Annotated[Principal, Requires(Scope.DELIVERIES_REPLAY)]


@router.get("")
async def list_endpoints(
    app_id: str,
    principal: Reader,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
    page: PageDep,
) -> Page[EndpointOut]:
    rows, cursor = await EndpointService(session, settings, clock).list_page(
        principal, app_id, before=page.before, limit=page.limit
    )
    return Page(data=rows, next_cursor=cursor)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    app_id: str,
    data: EndpointCreateIn,
    principal: Writer,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> EndpointOut:
    return await EndpointService(session, settings, clock).create(principal, app_id, data)


@router.get("/{endpoint_id}")
async def get_endpoint(
    app_id: str,
    endpoint_id: str,
    principal: Reader,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> EndpointOut:
    return await EndpointService(session, settings, clock).get(principal, app_id, endpoint_id)


@router.patch("/{endpoint_id}")
async def update_endpoint(
    app_id: str,
    endpoint_id: str,
    data: EndpointUpdateIn,
    principal: Writer,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> EndpointOut:
    return await EndpointService(session, settings, clock).update(
        principal, app_id, endpoint_id, data
    )


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    app_id: str,
    endpoint_id: str,
    principal: Writer,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> Response:
    await EndpointService(session, settings, clock).delete(principal, app_id, endpoint_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{endpoint_id}/enable")
async def enable_endpoint(
    app_id: str,
    endpoint_id: str,
    principal: Writer,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> EndpointOut:
    return await EndpointService(session, settings, clock).enable(principal, app_id, endpoint_id)


@router.get("/{endpoint_id}/secret")
async def get_endpoint_secret(
    app_id: str,
    endpoint_id: str,
    principal: Writer,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> EndpointSecretsOut:
    return await EndpointService(session, settings, clock).secrets(principal, app_id, endpoint_id)


@router.post("/{endpoint_id}/secret/rotate")
async def rotate_endpoint_secret(
    app_id: str,
    endpoint_id: str,
    data: RotateSecretIn,
    principal: Writer,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> EndpointSecretsOut:
    return await EndpointService(session, settings, clock).rotate_secret(
        principal, app_id, endpoint_id, data
    )


@router.get("/{endpoint_id}/stats")
async def endpoint_stats(
    app_id: str,
    endpoint_id: str,
    principal: Reader,
    session: SessionDep,
    clock: ClockDep,
    window: Annotated[StatsWindow, Query()] = "24h",
) -> LatencyStats:
    return await StatsService(session, clock).endpoint(principal, app_id, endpoint_id, window)


@router.post("/{endpoint_id}/replay")
async def replay_endpoint(
    app_id: str,
    endpoint_id: str,
    data: BulkReplayIn,
    principal: Replayer,
    session: SessionDep,
    clock: ClockDep,
) -> ReplayResultOut:
    scoped = data.model_copy(update={"endpoint_id": endpoint_id})
    count = await DeliveryService(session, clock).replay_bulk(principal, app_id, scoped)
    return ReplayResultOut(replayed=count)
