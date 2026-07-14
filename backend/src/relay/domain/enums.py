from enum import StrEnum


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    DEAD = "dead"


class AttemptOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AttemptTrigger(StrEnum):
    SCHEDULED = "scheduled"
    REPLAY = "replay"


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class Scope(StrEnum):
    APPS_READ = "apps:read"
    APPS_WRITE = "apps:write"
    ENDPOINTS_READ = "endpoints:read"
    ENDPOINTS_WRITE = "endpoints:write"
    EVENT_TYPES_READ = "event_types:read"
    EVENT_TYPES_WRITE = "event_types:write"
    MESSAGES_READ = "messages:read"
    MESSAGES_WRITE = "messages:write"
    DELIVERIES_REPLAY = "deliveries:replay"
    API_KEYS_MANAGE = "api_keys:manage"
    MEMBERS_MANAGE = "members:manage"
