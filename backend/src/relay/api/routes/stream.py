import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse, ServerSentEvent

from relay.api.deps import Requires, SessionDep, get_hub
from relay.auth.rbac import Principal
from relay.domain.enums import Scope
from relay.events.hub import LiveHub
from relay.services.access import load_app

router = APIRouter(prefix="/apps/{app_id}", tags=["live"])

_POLL_DISCONNECT_SECONDS = 5.0


@router.get("/stream", response_class=EventSourceResponse)
async def stream(
    app_id: str,
    request: Request,
    principal: Annotated[Principal, Requires(Scope.MESSAGES_READ)],
    session: SessionDep,
    hub: Annotated[LiveHub, Depends(get_hub)],
) -> EventSourceResponse:
    await load_app(session, principal, app_id)
    await session.close()

    async def events() -> AsyncIterator[ServerSentEvent]:
        async with hub.subscribe(app_id) as queue:
            yield ServerSentEvent(event="ready", data="{}")
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_POLL_DISCONNECT_SECONDS)
                except TimeoutError:
                    continue
                yield ServerSentEvent(event=event.kind, id=event.id, data=event.model_dump_json())

    return EventSourceResponse(events(), ping=15, headers={"x-accel-buffering": "no"})
