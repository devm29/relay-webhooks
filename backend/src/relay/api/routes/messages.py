from typing import Annotated

from fastapi import APIRouter, Header, Query, Response, status

from relay.api.deps import ClockDep, PageDep, Requires, SessionDep
from relay.auth.rbac import Principal
from relay.domain.enums import Scope
from relay.domain.models import (
    MessageCreatedOut,
    MessageCreateIn,
    MessageDetailOut,
    MessageOut,
    Page,
)
from relay.services.messages import MessageService

router = APIRouter(prefix="/apps/{app_id}/messages", tags=["messages"])

Reader = Annotated[Principal, Requires(Scope.MESSAGES_READ)]
Writer = Annotated[Principal, Requires(Scope.MESSAGES_WRITE)]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def publish_message(
    app_id: str,
    data: MessageCreateIn,
    principal: Writer,
    session: SessionDep,
    clock: ClockDep,
    response: Response,
    idempotency_key: Annotated[str | None, Header(max_length=255)] = None,
) -> MessageCreatedOut:
    result = await MessageService(session, clock).publish(
        principal, app_id, data, idempotency_key=idempotency_key
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
        response.headers["idempotent-replayed"] = "true"
    return result


@router.get("")
async def list_messages(
    app_id: str,
    principal: Reader,
    session: SessionDep,
    clock: ClockDep,
    page: PageDep,
    event_type: Annotated[str | None, Query(max_length=160)] = None,
) -> Page[MessageOut]:
    rows, cursor = await MessageService(session, clock).list_page(
        principal, app_id, event_type=event_type, before=page.before, limit=page.limit
    )
    return Page(data=rows, next_cursor=cursor)


@router.get("/{message_id}")
async def get_message(
    app_id: str, message_id: str, principal: Reader, session: SessionDep, clock: ClockDep
) -> MessageDetailOut:
    return await MessageService(session, clock).get(principal, app_id, message_id)
