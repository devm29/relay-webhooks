from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from relay.api.deps import ClockDep, PageDep, Requires, SessionDep
from relay.auth.rbac import Principal
from relay.domain.enums import Scope
from relay.domain.models import AppCreateIn, AppOut, AppOverviewOut, AppUpdateIn, Page, StatsWindow
from relay.services.catalog import AppService
from relay.services.stats import StatsService

router = APIRouter(prefix="/apps", tags=["apps"])

Reader = Annotated[Principal, Requires(Scope.APPS_READ)]
Writer = Annotated[Principal, Requires(Scope.APPS_WRITE)]


@router.get("")
async def list_apps(principal: Reader, session: SessionDep, page: PageDep) -> Page[AppOut]:
    rows, cursor = await AppService(session).list_page(
        principal, before=page.before, limit=page.limit
    )
    return Page(data=[AppOut.model_validate(a) for a in rows], next_cursor=cursor)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_app(data: AppCreateIn, principal: Writer, session: SessionDep) -> AppOut:
    return AppOut.model_validate(await AppService(session).create(principal, data))


@router.get("/{app_id}")
async def get_app(app_id: str, principal: Reader, session: SessionDep) -> AppOut:
    return AppOut.model_validate(await AppService(session).get(principal, app_id))


@router.patch("/{app_id}")
async def update_app(
    app_id: str, data: AppUpdateIn, principal: Writer, session: SessionDep
) -> AppOut:
    return AppOut.model_validate(await AppService(session).update(principal, app_id, data))


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_app(app_id: str, principal: Writer, session: SessionDep) -> Response:
    await AppService(session).delete(principal, app_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{app_id}/stats")
async def app_overview(
    app_id: str,
    principal: Reader,
    session: SessionDep,
    clock: ClockDep,
    window: Annotated[StatsWindow, Query()] = "24h",
) -> AppOverviewOut:
    return await StatsService(session, clock).overview(principal, app_id, window)
