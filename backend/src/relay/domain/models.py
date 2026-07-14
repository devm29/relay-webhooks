from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

from relay.domain.enums import (
    AttemptOutcome,
    AttemptTrigger,
    BreakerState,
    DeliveryStatus,
    Role,
    Scope,
)


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OutputModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FieldErrorOut(BaseModel):
    path: str
    message: str


class Page[T](BaseModel):
    data: list[T]
    next_cursor: str | None = None


Name = Annotated[str, StringConstraints(min_length=1, max_length=120)]
EventTypeName = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_\-]+(\.[a-zA-Z0-9_\-]+)*$"
    ),
]
Password = Annotated[str, StringConstraints(min_length=10, max_length=256)]


class SignupIn(InputModel):
    org_name: Name
    name: Name
    email: EmailStr
    password: Password


class LoginIn(InputModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_at: datetime


class OrgOut(OutputModel):
    id: str
    name: str
    created_at: datetime


class UserOut(OutputModel):
    id: str
    org_id: str
    email: str
    name: str
    role: Role
    created_at: datetime


class MeOut(BaseModel):
    user: UserOut | None
    org: OrgOut
    scopes: list[Scope]
    principal: Literal["user", "api_key"]


class MemberCreateIn(InputModel):
    email: EmailStr
    name: Name
    password: Password
    role: Role = Role.DEVELOPER


class MemberUpdateIn(InputModel):
    role: Role


class ApiKeyCreateIn(InputModel):
    name: Name
    scopes: Annotated[list[Scope], Field(min_length=1)]
    expires_in_days: Annotated[int, Field(ge=1, le=3650)] | None = None


class ApiKeyOut(OutputModel):
    id: str
    name: str
    prefix: str
    scopes: list[Scope]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreatedOut(ApiKeyOut):
    key: str


class AppCreateIn(InputModel):
    name: Name
    description: Annotated[str, StringConstraints(max_length=500)] | None = None


class AppUpdateIn(InputModel):
    name: Name | None = None
    description: Annotated[str, StringConstraints(max_length=500)] | None = None


class AppOut(OutputModel):
    id: str
    name: str
    description: str | None
    created_at: datetime


class EventTypeCreateIn(InputModel):
    name: EventTypeName
    description: Annotated[str, StringConstraints(max_length=500)] | None = None
    payload_schema: dict[str, Any] | None = None


class EventTypeUpdateIn(InputModel):
    description: Annotated[str, StringConstraints(max_length=500)] | None = None
    payload_schema: dict[str, Any] | None = None
    archived: bool | None = None


class EventTypeOut(OutputModel):
    id: str
    name: str
    description: str | None
    payload_schema: dict[str, Any] | None
    version: int
    archived: bool
    created_at: datetime
    updated_at: datetime


def _check_secret(value: str | None) -> str | None:
    if value is not None and not value.startswith("whsec_"):
        raise ValueError("secret must start with whsec_")
    return value


# Framing, hop-by-hop and signature headers are Relay's to set; letting a tenant override
# them would allow request smuggling or forged signatures.
RESERVED_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "content-type",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "upgrade",
        "te",
        "trailer",
        "expect",
        "proxy-authorization",
        "proxy-connection",
        "user-agent",
        "webhook-id",
        "webhook-timestamp",
        "webhook-signature",
    }
)


def _check_headers(headers: dict[str, str]) -> dict[str, str]:
    reserved = sorted(name for name in headers if name.lower() in RESERVED_HEADERS)
    if reserved:
        raise ValueError(f"these headers are managed by Relay: {', '.join(reserved)}")
    if len({name.lower() for name in headers}) != len(headers):
        raise ValueError("header names must be unique, ignoring case")
    return headers


HeaderMap = Annotated[
    dict[
        Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9-]{1,64}$")],
        Annotated[str, StringConstraints(max_length=1024, pattern=r"^[^\r\n]*$")],
    ],
    Field(max_length=20),
    AfterValidator(_check_headers),
]
RatePerSecond = Annotated[float, Field(gt=0, le=1000)]
MAX_ENDPOINT_TIMEOUT_SECONDS = 30.0
TimeoutSeconds = Annotated[float, Field(gt=0, le=MAX_ENDPOINT_TIMEOUT_SECONDS)]
EndpointName = Annotated[str, StringConstraints(min_length=1, max_length=120)]


class EndpointCreateIn(InputModel):
    url: AnyHttpUrl
    name: EndpointName | None = None
    description: Annotated[str, StringConstraints(max_length=500)] | None = None
    event_types: list[EventTypeName] = Field(default_factory=list)
    rate_limit_per_second: RatePerSecond | None = None
    timeout_seconds: TimeoutSeconds | None = None
    headers: HeaderMap = Field(default_factory=dict)
    secret: str | None = None
    disabled: bool = False

    _validate_secret = field_validator("secret")(_check_secret)


class EndpointUpdateIn(InputModel):
    url: AnyHttpUrl | None = None
    name: EndpointName | None = None
    description: Annotated[str, StringConstraints(max_length=500)] | None = None
    event_types: list[EventTypeName] | None = None
    rate_limit_per_second: RatePerSecond | None = None
    timeout_seconds: TimeoutSeconds | None = None
    headers: HeaderMap | None = None
    disabled: bool | None = None


class BreakerOut(OutputModel):
    state: BreakerState
    consecutive_failures: int
    trip_count: int
    opened_at: datetime | None
    open_until: datetime | None


class EndpointOut(OutputModel):
    id: str
    app_id: str
    name: str | None
    url: str
    description: str | None
    event_types: list[str]
    rate_limit_per_second: float | None
    timeout_seconds: float | None
    headers: dict[str, str]
    disabled: bool
    disabled_reason: str | None
    created_at: datetime
    updated_at: datetime
    breaker: BreakerOut | None = None


class RotateSecretIn(InputModel):
    secret: str | None = None
    overlap_seconds: Annotated[int, Field(ge=0, le=7 * 86_400)] | None = None

    _validate_secret = field_validator("secret")(_check_secret)


class SecretOut(OutputModel):
    id: str
    secret: str
    created_at: datetime
    expires_at: datetime | None


class EndpointSecretsOut(BaseModel):
    current: SecretOut
    previous: list[SecretOut]


class MessageCreateIn(InputModel):
    event_type: EventTypeName
    payload: dict[str, Any]
    event_id: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None


class MessageOut(OutputModel):
    id: str
    app_id: str
    event_type: str
    event_id: str | None
    payload: dict[str, Any]
    created_at: datetime


class MessageCreatedOut(MessageOut):
    fanout: int
    idempotent_replay: bool = False


class DeliveryOut(OutputModel):
    id: str
    app_id: str
    message_id: str
    endpoint_id: str
    status: DeliveryStatus
    attempt_count: int
    next_attempt_at: datetime | None
    last_status_code: int | None
    last_error: str | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    event_type: str
    endpoint_url: str


class AttemptOut(OutputModel):
    id: str
    delivery_id: str
    message_id: str
    endpoint_id: str
    attempt_number: int
    trigger: AttemptTrigger
    outcome: AttemptOutcome
    status_code: int | None
    error: str | None
    response_snippet: str | None
    latency_ms: int
    started_at: datetime
    next_attempt_at: datetime | None


class AttemptLogOut(AttemptOut):
    event_type: str
    endpoint_url: str
    delivery_status: DeliveryStatus


class DeliveryDetailOut(DeliveryOut):
    payload: dict[str, Any]
    attempts: list[AttemptOut]


class MessageDetailOut(MessageOut):
    deliveries: list[DeliveryOut]


class BulkReplayIn(InputModel):
    endpoint_id: str | None = None
    status: Literal["dead", "succeeded"] = "dead"
    since: datetime | None = None
    until: datetime | None = None


class ReplayResultOut(BaseModel):
    replayed: int


StatsWindow = Literal["1h", "24h", "7d"]


class StatsBucket(BaseModel):
    ts: datetime
    total: int
    succeeded: int
    failed: int
    p50_ms: float | None
    p95_ms: float | None


class LatencyStats(BaseModel):
    window: StatsWindow
    total: int
    succeeded: int
    failed: int
    success_rate: float | None
    p50_ms: float | None
    p95_ms: float | None
    series: list[StatsBucket]


class EndpointHealthCounts(BaseModel):
    total: int
    healthy: int
    degraded: int
    open: int
    disabled: int


class AppOverviewOut(LatencyStats):
    messages: int
    pending: int
    dead: int
    endpoints: EndpointHealthCounts


class LiveEvent(BaseModel):
    kind: Literal["attempt", "message"]
    app_id: str
    id: str
    message_id: str
    event_type: str
    endpoint_id: str | None = None
    delivery_id: str | None = None
    outcome: AttemptOutcome | None = None
    status_code: int | None = None
    latency_ms: int | None = None
    attempt_number: int | None = None
    delivery_status: DeliveryStatus | None = None
    at: datetime
