from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Query, Request, params
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from relay.auth.rbac import Principal
from relay.auth.throttle import LoginThrottle
from relay.clock import Clock
from relay.config import Settings
from relay.domain.enums import Scope
from relay.domain.errors import AuthenticationError, PermissionDeniedError
from relay.events.hub import LiveHub
from relay.persistence.repositories.base import clamp_limit
from relay.services.auth import AuthService

_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_hub(request: Request) -> LiveHub:
    hub: LiveHub = request.app.state.hub
    return hub


def get_login_throttle(request: Request) -> LoginThrottle:
    throttle: LoginThrottle = request.app.state.login_throttle
    return throttle


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.sessions
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ClockDep = Annotated[Clock, Depends(get_clock)]
ThrottleDep = Annotated[LoginThrottle, Depends(get_login_throttle)]


async def get_principal(
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("missing bearer token")
    return await AuthService(session, settings, clock).authenticate(credentials.credentials)


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require(scope: Scope) -> Callable[[Principal], Coroutine[Any, Any, Principal]]:
    async def dependency(principal: PrincipalDep) -> Principal:
        if not principal.can(scope):
            raise PermissionDeniedError(f"missing required scope {scope.value}")
        return principal

    return dependency


def Requires(scope: Scope) -> params.Depends:  # noqa: N802
    dependency: params.Depends = Depends(require(scope))
    return dependency


class PageParams:
    def __init__(
        self,
        limit: Annotated[int | None, Query(ge=1, le=200)] = None,
        before: Annotated[str | None, Query(max_length=40)] = None,
    ) -> None:
        self.limit = clamp_limit(limit)
        self.before = before


PageDep = Annotated[PageParams, Depends()]
