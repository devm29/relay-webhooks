from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relay.auth.api_keys import generate_api_key, hash_api_key, looks_like_api_key
from relay.auth.passwords import hash_password, hash_password_async, verify_password_async
from relay.auth.rbac import ROLE_SCOPES, Principal, can_assign_role
from relay.auth.tokens import decode_session_token, issue_session_token
from relay.clock import Clock
from relay.config import Settings
from relay.domain.enums import Role, Scope
from relay.domain.errors import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from relay.domain.models import (
    ApiKeyCreatedOut,
    ApiKeyCreateIn,
    ApiKeyOut,
    LoginIn,
    MemberCreateIn,
    MeOut,
    OrgOut,
    SignupIn,
    TokenOut,
    UserOut,
)
from relay.ids import new_id
from relay.persistence.repositories.tenants import ApiKeyRepository, OrgRepository, UserRepository
from relay.persistence.tables import ApiKey, Org, User

# Recording every use would turn each authenticated read into a write.
_TOUCH_INTERVAL = timedelta(minutes=1)

# Verifying against a real hash keeps login timing the same whether or not the email exists.
_DUMMY_HASH = hash_password("relay-timing-equalizer")


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings, clock: Clock) -> None:
        self.session = session
        self.settings = settings
        self.clock = clock
        self.users = UserRepository(session)
        self.orgs = OrgRepository(session)
        self.keys = ApiKeyRepository(session)

    def _issue(self, user: User) -> TokenOut:
        token, expires_at = issue_session_token(
            user_id=user.id,
            org_id=user.org_id,
            role=Role(user.role),
            secret=self.settings.jwt_secret.get_secret_value(),
            ttl=timedelta(minutes=self.settings.jwt_ttl_minutes),
            now=self.clock.now(),
        )
        return TokenOut(access_token=token, expires_at=expires_at)

    async def signup(self, data: SignupIn) -> TokenOut:
        org = await self.orgs.add(Org(id=new_id("org"), name=data.org_name))
        user = User(
            id=new_id("usr"),
            org_id=org.id,
            email=data.email.lower(),
            name=data.name,
            password_hash=await hash_password_async(data.password),
            role=Role.OWNER.value,
        )
        try:
            await self.users.add(user)
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("an account with this email already exists") from exc
        await self.session.commit()
        return self._issue(user)

    async def login(self, data: LoginIn) -> TokenOut:
        user = await self.users.by_email(data.email)
        if user is None:
            await verify_password_async(_DUMMY_HASH, data.password)
            raise AuthenticationError("incorrect email or password")
        if not await verify_password_async(user.password_hash, data.password):
            raise AuthenticationError("incorrect email or password")
        return self._issue(user)

    async def authenticate(self, token: str) -> Principal:
        if looks_like_api_key(token):
            return await self._authenticate_key(token)
        claims = decode_session_token(
            token, self.settings.jwt_secret.get_secret_value(), self.clock.now()
        )
        user = await self.users.get(claims.org, claims.sub)
        if user is None:
            raise AuthenticationError("session user no longer exists")
        role = Role(user.role)
        return Principal(
            kind="user", subject_id=user.id, org_id=user.org_id, scopes=ROLE_SCOPES[role], role=role
        )

    async def _authenticate_key(self, token: str) -> Principal:
        key = await self.keys.by_hash(
            hash_api_key(token, self.settings.api_key_pepper.get_secret_value())
        )
        now = self.clock.now()
        if key is None or key.revoked_at is not None:
            raise AuthenticationError("invalid API key")
        if key.expires_at is not None and key.expires_at <= now:
            raise AuthenticationError("API key has expired")
        if key.last_used_at is None or now - key.last_used_at > _TOUCH_INTERVAL:
            await self.keys.touch(key.id, now)
            await self.session.commit()
        return Principal(
            kind="api_key",
            subject_id=key.id,
            org_id=key.org_id,
            scopes=frozenset(Scope(s) for s in key.scopes),
        )

    async def me(self, principal: Principal) -> MeOut:
        org = await self.orgs.get(principal.org_id)
        if org is None:
            raise AuthenticationError("organization no longer exists")
        user = (
            await self.users.get(principal.org_id, principal.subject_id)
            if principal.kind == "user"
            else None
        )
        return MeOut(
            user=UserOut.model_validate(user) if user else None,
            org=OrgOut.model_validate(org),
            scopes=sorted(principal.scopes),
            principal=principal.kind,
        )


class MemberService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def list_all(self, principal: Principal) -> list[User]:
        return await self.users.list_for_org(principal.org_id)

    async def create(self, principal: Principal, data: MemberCreateIn) -> User:
        self._check_can_assign(principal, data.role)
        user = User(
            id=new_id("usr"),
            org_id=principal.org_id,
            email=data.email.lower(),
            name=data.name,
            password_hash=await hash_password_async(data.password),
            role=data.role.value,
        )
        try:
            await self.users.add(user)
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("an account with this email already exists") from exc
        await self.session.commit()
        return user

    async def update_role(self, principal: Principal, user_id: str, role: Role) -> User:
        user = await self.users.get(principal.org_id, user_id)
        if user is None:
            raise NotFoundError(f"member {user_id} not found")
        if user.id == principal.subject_id:
            raise PermissionDeniedError("you cannot change your own role")
        self._check_can_assign(principal, Role(user.role))
        self._check_can_assign(principal, role)
        user.role = role.value
        await self.session.commit()
        return user

    @staticmethod
    def _check_can_assign(principal: Principal, role: Role) -> None:
        if principal.role is None or not can_assign_role(principal.role, role):
            raise PermissionDeniedError(f"your role cannot manage {role.value} members")


class ApiKeyService:
    def __init__(self, session: AsyncSession, settings: Settings, clock: Clock) -> None:
        self.session = session
        self.settings = settings
        self.clock = clock
        self.keys = ApiKeyRepository(session)

    async def create(self, principal: Principal, data: ApiKeyCreateIn) -> ApiKeyCreatedOut:
        excess = set(data.scopes) - principal.scopes
        if excess:
            names = ", ".join(sorted(excess))
            raise PermissionDeniedError(f"you cannot grant scopes you do not hold: {names}")
        generated = generate_api_key(self.settings.api_key_pepper.get_secret_value())
        now = self.clock.now()
        key = await self.keys.add(
            ApiKey(
                id=new_id("key"),
                org_id=principal.org_id,
                name=data.name,
                prefix=generated.prefix,
                key_hash=generated.key_hash,
                scopes=sorted({s.value for s in data.scopes}),
                created_by=principal.subject_id if principal.kind == "user" else None,
                created_at=now,
                expires_at=now + timedelta(days=data.expires_in_days)
                if data.expires_in_days
                else None,
            )
        )
        await self.session.commit()
        return ApiKeyCreatedOut.model_validate(
            {**ApiKeyOut.model_validate(key).model_dump(), "key": generated.plaintext}
        )

    async def list_all(self, principal: Principal) -> list[ApiKey]:
        return await self.keys.list_for_org(principal.org_id)

    async def revoke(self, principal: Principal, key_id: str) -> ApiKey:
        key = await self.keys.get(principal.org_id, key_id)
        if key is None:
            raise NotFoundError(f"API key {key_id} not found")
        if key.revoked_at is None:
            key.revoked_at = self.clock.now()
            await self.session.commit()
        return key
