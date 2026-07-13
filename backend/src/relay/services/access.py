from sqlalchemy.ext.asyncio import AsyncSession

from relay.auth.rbac import Principal
from relay.domain.errors import NotFoundError
from relay.persistence.repositories.tenants import AppRepository
from relay.persistence.tables import App


async def load_app(session: AsyncSession, principal: Principal, app_id: str) -> App:
    app = await AppRepository(session).get(principal.org_id, app_id)
    if app is None:
        raise NotFoundError(f"app {app_id} not found")
    return app
