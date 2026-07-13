from typing import Annotated

from fastapi import APIRouter, Request, status

from relay.api.deps import (
    ClockDep,
    PrincipalDep,
    Requires,
    SessionDep,
    SettingsDep,
    ThrottleDep,
)
from relay.api.errors import ErrorResponse
from relay.auth.rbac import Principal
from relay.domain.enums import Scope
from relay.domain.models import (
    ApiKeyCreatedOut,
    ApiKeyCreateIn,
    ApiKeyOut,
    LoginIn,
    MemberCreateIn,
    MemberUpdateIn,
    MeOut,
    SignupIn,
    TokenOut,
    UserOut,
)
from relay.services.auth import ApiKeyService, AuthService, MemberService

router = APIRouter(tags=["auth"])

MembersManager = Annotated[Principal, Requires(Scope.MEMBERS_MANAGE)]
KeysManager = Annotated[Principal, Requires(Scope.API_KEYS_MANAGE)]


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post(
    "/auth/signup",
    status_code=status.HTTP_201_CREATED,
    responses={429: {"model": ErrorResponse}},
)
async def signup(
    data: SignupIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
    throttle: ThrottleDep,
) -> TokenOut:
    throttle.check_signup(_client(request), clock.now())
    return await AuthService(session, settings, clock).signup(data)


@router.post("/auth/login", responses={429: {"model": ErrorResponse}})
async def login(
    data: LoginIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
    throttle: ThrottleDep,
) -> TokenOut:
    throttle.check_login(_client(request), data.email, clock.now())
    return await AuthService(session, settings, clock).login(data)


@router.get("/auth/me")
async def me(
    principal: PrincipalDep, session: SessionDep, settings: SettingsDep, clock: ClockDep
) -> MeOut:
    return await AuthService(session, settings, clock).me(principal)


@router.get("/members")
async def list_members(
    principal: Annotated[Principal, Requires(Scope.APPS_READ)], session: SessionDep
) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in await MemberService(session).list_all(principal)]


@router.post("/members", status_code=status.HTTP_201_CREATED)
async def create_member(
    data: MemberCreateIn, principal: MembersManager, session: SessionDep
) -> UserOut:
    return UserOut.model_validate(await MemberService(session).create(principal, data))


@router.patch("/members/{user_id}")
async def update_member(
    user_id: str, data: MemberUpdateIn, principal: MembersManager, session: SessionDep
) -> UserOut:
    user = await MemberService(session).update_role(principal, user_id, data.role)
    return UserOut.model_validate(user)


@router.get("/api-keys")
async def list_api_keys(
    principal: KeysManager, session: SessionDep, settings: SettingsDep, clock: ClockDep
) -> list[ApiKeyOut]:
    keys = await ApiKeyService(session, settings, clock).list_all(principal)
    return [ApiKeyOut.model_validate(k) for k in keys]


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: ApiKeyCreateIn,
    principal: KeysManager,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> ApiKeyCreatedOut:
    return await ApiKeyService(session, settings, clock).create(principal, data)


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    principal: KeysManager,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> ApiKeyOut:
    key = await ApiKeyService(session, settings, clock).revoke(principal, key_id)
    return ApiKeyOut.model_validate(key)
