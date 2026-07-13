from typing import Annotated

from fastapi import APIRouter, Query

from relay.api.deps import ClockDep, PageDep, Requires, SessionDep
from relay.auth.rbac import Principal
from relay.domain.enums import DeliveryStatus, Scope
from relay.domain.models import (
    AttemptLogOut,
    BulkReplayIn,
    DeliveryDetailOut,
    DeliveryOut,
    Page,
    ReplayResultOut,
)
from relay.services.messages import DeliveryService

router = APIRouter(prefix="/apps/{app_id}", tags=["deliveries"])

Reader = Annotated[Principal, Requires(Scope.MESSAGES_READ)]
Replayer = Annotated[Principal, Requires(Scope.DELIVERIES_REPLAY)]


@router.get("/deliveries")
async def list_deliveries(
    app_id: str,
    principal: Reader,
    session: SessionDep,
    clock: ClockDep,
    page: PageDep,
    status: Annotated[DeliveryStatus | None, Query()] = None,
    endpoint_id: Annotated[str | None, Query(max_length=40)] = None,
) -> Page[DeliveryOut]:
    rows, cursor = await DeliveryService(session, clock).list_page(
        principal,
        app_id,
        status=status,
        endpoint_id=endpoint_id,
        before=page.before,
        limit=page.limit,
    )
    return Page(data=rows, next_cursor=cursor)


@router.post("/deliveries/replay")
async def replay_deliveries(
    app_id: str, data: BulkReplayIn, principal: Replayer, session: SessionDep, clock: ClockDep
) -> ReplayResultOut:
    count = await DeliveryService(session, clock).replay_bulk(principal, app_id, data)
    return ReplayResultOut(replayed=count)


@router.get("/deliveries/{delivery_id}")
async def get_delivery(
    app_id: str, delivery_id: str, principal: Reader, session: SessionDep, clock: ClockDep
) -> DeliveryDetailOut:
    return await DeliveryService(session, clock).get(principal, app_id, delivery_id)


@router.post("/deliveries/{delivery_id}/replay")
async def replay_delivery(
    app_id: str, delivery_id: str, principal: Replayer, session: SessionDep, clock: ClockDep
) -> DeliveryOut:
    return await DeliveryService(session, clock).replay(principal, app_id, delivery_id)


@router.get("/attempts")
async def attempt_log(
    app_id: str,
    principal: Reader,
    session: SessionDep,
    clock: ClockDep,
    page: PageDep,
    endpoint_id: Annotated[str | None, Query(max_length=40)] = None,
) -> Page[AttemptLogOut]:
    rows, cursor = await DeliveryService(session, clock).attempt_log(
        principal, app_id, endpoint_id=endpoint_id, before=page.before, limit=page.limit
    )
    return Page(data=rows, next_cursor=cursor)
