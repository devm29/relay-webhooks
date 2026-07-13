from dataclasses import dataclass
from typing import Literal

from relay.domain.enums import Role, Scope

_READ = frozenset(
    {
        Scope.APPS_READ,
        Scope.ENDPOINTS_READ,
        Scope.EVENT_TYPES_READ,
        Scope.MESSAGES_READ,
    }
)
_DEVELOPER = _READ | {
    Scope.ENDPOINTS_WRITE,
    Scope.EVENT_TYPES_WRITE,
    Scope.MESSAGES_WRITE,
    Scope.DELIVERIES_REPLAY,
}
_ADMIN = _DEVELOPER | {Scope.APPS_WRITE, Scope.API_KEYS_MANAGE, Scope.MEMBERS_MANAGE}

ROLE_SCOPES: dict[Role, frozenset[Scope]] = {
    Role.VIEWER: _READ,
    Role.DEVELOPER: _DEVELOPER,
    Role.ADMIN: _ADMIN,
    Role.OWNER: frozenset(Scope),
}

ROLE_RANK = {Role.VIEWER: 0, Role.DEVELOPER: 1, Role.ADMIN: 2, Role.OWNER: 3}


@dataclass(frozen=True, slots=True)
class Principal:
    kind: Literal["user", "api_key"]
    subject_id: str
    org_id: str
    scopes: frozenset[Scope]
    role: Role | None = None

    def can(self, scope: Scope) -> bool:
        return scope in self.scopes


def can_assign_role(actor: Role, target: Role) -> bool:
    if actor is Role.OWNER:
        return True
    return ROLE_RANK[target] < ROLE_RANK[actor]
