from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from relay.persistence.repositories.base import paginate_desc, split_page
from relay.persistence.tables import ApiKey, App, Org, User


class OrgRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, org: Org) -> Org:
        self.session.add(org)
        await self.session.flush()
        return org

    async def get(self, org_id: str) -> Org | None:
        return await self.session.get(Org, org_id)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def get(self, org_id: str, user_id: str) -> User | None:
        stmt = select(User).where(User.org_id == org_id, User.id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_org(self, org_id: str) -> list[User]:
        stmt = select(User).where(User.org_id == org_id).order_by(User.created_at)
        return list((await self.session.execute(stmt)).scalars())


class AppRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, app: App) -> App:
        self.session.add(app)
        await self.session.flush()
        return app

    async def get(self, org_id: str, app_id: str) -> App | None:
        stmt = select(App).where(App.org_id == org_id, App.id == app_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def by_name(self, org_id: str, name: str) -> App | None:
        stmt = select(App).where(App.org_id == org_id, App.name == name)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_page(
        self, org_id: str, *, before: str | None, limit: int
    ) -> tuple[list[App], str | None]:
        stmt = paginate_desc(
            select(App).where(App.org_id == org_id), App.id, before=before, limit=limit
        )
        rows = list((await self.session.execute(stmt)).scalars())
        return split_page(rows, limit)

    async def delete(self, app: App) -> None:
        await self.session.delete(app)


class ApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, key: ApiKey) -> ApiKey:
        self.session.add(key)
        await self.session.flush()
        return key

    async def by_hash(self, key_hash: str) -> ApiKey | None:
        stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get(self, org_id: str, key_id: str) -> ApiKey | None:
        stmt = select(ApiKey).where(ApiKey.org_id == org_id, ApiKey.id == key_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_org(self, org_id: str) -> list[ApiKey]:
        stmt = select(ApiKey).where(ApiKey.org_id == org_id).order_by(ApiKey.id.desc())
        return list((await self.session.execute(stmt)).scalars())

    async def touch(self, key_id: str, now: datetime) -> None:
        await self.session.execute(
            update(ApiKey).where(ApiKey.id == key_id).values(last_used_at=now)
        )
