from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from relay.api.deps import ClockDep, Requires, SessionDep
from relay.auth.rbac import Principal
from relay.domain.enums import Scope
from relay.domain.models import EventTypeCreateIn, EventTypeOut, EventTypeUpdateIn
from relay.services.catalog import EventTypeService

router = APIRouter(prefix="/apps/{app_id}/event-types", tags=["event types"])

Reader = Annotated[Principal, Requires(Scope.EVENT_TYPES_READ)]
Writer = Annotated[Principal, Requires(Scope.EVENT_TYPES_WRITE)]


@router.get("")
async def list_event_types(
    app_id: str,
    principal: Reader,
    session: SessionDep,
    clock: ClockDep,
    include_archived: Annotated[bool, Query()] = False,
) -> list[EventTypeOut]:
    rows = await EventTypeService(session, clock).list_all(
        principal, app_id, include_archived=include_archived
    )
    return [EventTypeOut.model_validate(e) for e in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_event_type(
    app_id: str, data: EventTypeCreateIn, principal: Writer, session: SessionDep, clock: ClockDep
) -> EventTypeOut:
    return EventTypeOut.model_validate(
        await EventTypeService(session, clock).create(principal, app_id, data)
    )


@router.get("/{name}")
async def get_event_type(
    app_id: str, name: str, principal: Reader, session: SessionDep, clock: ClockDep
) -> EventTypeOut:
    return EventTypeOut.model_validate(
        await EventTypeService(session, clock).get(principal, app_id, name)
    )


@router.patch("/{name}")
async def update_event_type(
    app_id: str,
    name: str,
    data: EventTypeUpdateIn,
    principal: Writer,
    session: SessionDep,
    clock: ClockDep,
) -> EventTypeOut:
    return EventTypeOut.model_validate(
        await EventTypeService(session, clock).update(principal, app_id, name, data)
    )


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event_type(
    app_id: str, name: str, principal: Writer, session: SessionDep, clock: ClockDep
) -> Response:
    await EventTypeService(session, clock).delete(principal, app_id, name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
