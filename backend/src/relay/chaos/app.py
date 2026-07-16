"""A deliberately unreliable webhook receiver for demos and soak tests.

Behaviour comes from query parameters on the endpoint URL (so each Relay endpoint can
be a different flavour of broken) and can be overridden per receiver name at runtime
through the control API, e.g. to stage an outage and watch the breaker open.
"""

import asyncio
import json
import random
from collections import deque
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request, Response, status
from pydantic import BaseModel, Field

from relay.signing import Webhook, WebhookVerificationError


class Scenario(BaseModel):
    fail_rate: Annotated[float, Field(ge=0, le=1)] = 0.0
    fail_status: Annotated[int, Field(ge=400, le=599)] = 500
    timeout_rate: Annotated[float, Field(ge=0, le=1)] = 0.0
    hang_seconds: Annotated[float, Field(ge=0, le=120)] = 35.0
    latency_ms: Annotated[int, Field(ge=0, le=30_000)] = 0
    jitter_ms: Annotated[int, Field(ge=0, le=30_000)] = 0
    retry_after: Annotated[int, Field(ge=0, le=3600)] | None = None
    gone: bool = False


class Received(BaseModel):
    receiver: str
    webhook_id: str | None
    event_type: str | None
    signature: Literal["valid", "invalid", "unchecked"]
    responded: int | Literal["timeout"]
    latency_ms: int
    at: datetime


class ChaosState:
    def __init__(self, verify_secret: str | None, inbox_size: int = 500) -> None:
        self.overrides: dict[str, Scenario] = {}
        self.inbox: deque[Received] = deque(maxlen=inbox_size)
        self.verifier = Webhook(verify_secret) if verify_secret else None
        self.rng = random.Random()


def create_chaos_app(verify_secret: str | None = None) -> FastAPI:
    app = FastAPI(title="Relay chaos receiver", version="0.1.0")
    state = ChaosState(verify_secret)

    @app.post("/hooks/{name}")
    async def receive(name: str, request: Request, query: Annotated[Scenario, Query()]) -> Response:
        scenario = state.overrides.get(name, query)
        body = await request.body()
        signature: Literal["valid", "invalid", "unchecked"] = "unchecked"
        if state.verifier is not None:
            try:
                state.verifier.verify(body, dict(request.headers))
                signature = "valid"
            except WebhookVerificationError:
                signature = "invalid"

        delay_ms = scenario.latency_ms + state.rng.randint(0, scenario.jitter_ms)
        roll = state.rng.random()
        responded: int | Literal["timeout"]
        if scenario.gone:
            responded = status.HTTP_410_GONE
        elif roll < scenario.timeout_rate:
            responded = "timeout"
            delay_ms = int(scenario.hang_seconds * 1000)
        elif roll < scenario.timeout_rate + scenario.fail_rate:
            responded = scenario.fail_status
        elif signature == "invalid":
            responded = status.HTTP_401_UNAUTHORIZED
        else:
            responded = status.HTTP_200_OK

        state.inbox.appendleft(
            Received(
                receiver=name,
                webhook_id=request.headers.get("webhook-id"),
                event_type=_event_type(body),
                signature=signature,
                responded=responded,
                latency_ms=delay_ms,
                at=datetime.now(UTC),
            )
        )
        if delay_ms:
            await asyncio.sleep(delay_ms / 1000)

        code = status.HTTP_504_GATEWAY_TIMEOUT if responded == "timeout" else responded
        headers = {}
        if code >= 400 and scenario.retry_after is not None:
            headers["retry-after"] = str(scenario.retry_after)
        content = '{"ok":true}' if code < 300 else f'{{"error":"chaos says {code}"}}'
        return Response(content, status_code=code, media_type="application/json", headers=headers)

    @app.get("/inbox")
    async def inbox(limit: Annotated[int, Query(ge=1, le=500)] = 50) -> list[Received]:
        return list(state.inbox)[:limit]

    @app.get("/control/scenarios")
    async def list_overrides() -> dict[str, Scenario]:
        return state.overrides

    @app.put("/control/scenarios/{name}")
    async def set_override(name: str, scenario: Scenario) -> Scenario:
        state.overrides[name] = scenario
        return scenario

    @app.delete("/control/scenarios/{name}", status_code=status.HTTP_204_NO_CONTENT)
    async def clear_override(name: str) -> Response:
        state.overrides.pop(name, None)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _event_type(body: bytes) -> str | None:
    try:
        parsed = json.loads(body)
    except ValueError:
        return None
    value = parsed.get("type") if isinstance(parsed, dict) else None
    return value if isinstance(value, str) else None
