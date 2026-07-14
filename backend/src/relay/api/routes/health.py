from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from relay.api.deps import SessionDep, get_hub
from relay.events.hub import LiveHub

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
    live_subscribers: int


@router.get("/healthz")
async def healthz(session: SessionDep, hub: Annotated[LiveHub, Depends(get_hub)]) -> Health:
    await session.execute(text("SELECT 1"))
    return Health(status="ok", database="ok", live_subscribers=hub.subscriber_count())
