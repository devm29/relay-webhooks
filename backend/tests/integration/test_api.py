import asyncio
import json
import socket
from collections.abc import AsyncIterator

import httpx
import pytest
import uvicorn

from relay.api.app import create_app
from relay.config import Settings
from relay.dispatcher.runner import Dispatcher
from tests.support import FakeClock

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery"


async def _signup(api: httpx.AsyncClient, email: str, org: str = "Acme") -> dict[str, str]:
    response = await api.post(
        "/api/v1/auth/signup",
        json={"org_name": org, "name": "Ada", "email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return {"authorization": f"Bearer {response.json()['access_token']}"}


async def _app(api: httpx.AsyncClient, headers: dict[str, str], name: str = "Billing") -> str:
    response = await api.post("/api/v1/apps", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def test_signup_login_and_me(api: httpx.AsyncClient) -> None:
    await _signup(api, "ada@acme.dev")
    bad = await api.post("/api/v1/auth/login", json={"email": "ada@acme.dev", "password": "nope"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "unauthenticated"

    good = await api.post(
        "/api/v1/auth/login", json={"email": "ADA@acme.dev", "password": PASSWORD}
    )
    assert good.status_code == 200
    me = await api.get(
        "/api/v1/auth/me", headers={"authorization": f"Bearer {good.json()['access_token']}"}
    )
    assert me.json()["user"]["role"] == "owner"
    assert "api_keys:manage" in me.json()["scopes"]

    duplicate = await api.post(
        "/api/v1/auth/signup",
        json={"org_name": "X", "name": "Y", "email": "ada@acme.dev", "password": PASSWORD},
    )
    assert duplicate.status_code == 409


async def test_tenants_cannot_see_each_other(api: httpx.AsyncClient) -> None:
    acme = await _signup(api, "ops@acme.dev")
    globex = await _signup(api, "ops@globex.dev", org="Globex")
    app_id = await _app(api, acme)

    assert (await api.get(f"/api/v1/apps/{app_id}", headers=globex)).status_code == 404
    listed = await api.get("/api/v1/apps", headers=globex)
    assert listed.json()["data"] == []
    sneaky = await api.post(
        f"/api/v1/apps/{app_id}/endpoints", json={"url": "https://x.example.com"}, headers=globex
    )
    assert sneaky.status_code == 404


async def test_roles_and_api_key_scopes_are_enforced(api: httpx.AsyncClient) -> None:
    owner = await _signup(api, "owner@acme.dev")
    app_id = await _app(api, owner)
    await api.post(
        f"/api/v1/apps/{app_id}/event-types", json={"name": "order.created"}, headers=owner
    )

    created = await api.post(
        "/api/v1/members",
        json={"email": "viewer@acme.dev", "name": "Vi", "password": PASSWORD, "role": "viewer"},
        headers=owner,
    )
    assert created.status_code == 201
    login = await api.post(
        "/api/v1/auth/login", json={"email": "viewer@acme.dev", "password": PASSWORD}
    )
    viewer = {"authorization": f"Bearer {login.json()['access_token']}"}
    assert (await api.get(f"/api/v1/apps/{app_id}/endpoints", headers=viewer)).status_code == 200
    denied = await api.post(
        f"/api/v1/apps/{app_id}/endpoints", json={"url": "https://x.example.com"}, headers=viewer
    )
    assert denied.status_code == 403

    key = await api.post(
        "/api/v1/api-keys", json={"name": "backend", "scopes": ["messages:write"]}, headers=owner
    )
    assert key.status_code == 201
    api_key = {"authorization": f"Bearer {key.json()['key']}"}
    published = await api.post(
        f"/api/v1/apps/{app_id}/messages",
        json={"event_type": "order.created", "payload": {"id": 1}},
        headers=api_key,
    )
    assert published.status_code == 202
    assert (await api.get(f"/api/v1/apps/{app_id}/endpoints", headers=api_key)).status_code == 403

    listed = await api.get("/api/v1/api-keys", headers=owner)
    [summary] = listed.json()
    assert "key" not in summary
    assert summary["last_used_at"] is not None

    await api.delete(f"/api/v1/api-keys/{summary['id']}", headers=owner)
    revoked = await api.post(
        f"/api/v1/apps/{app_id}/messages",
        json={"event_type": "order.created", "payload": {"id": 2}},
        headers=api_key,
    )
    assert revoked.status_code == 401


async def test_publish_validation_pagination_and_delivery_views(
    api: httpx.AsyncClient, dispatcher: Dispatcher
) -> None:
    owner = await _signup(api, "dev@acme.dev")
    app_id = await _app(api, owner)
    base = f"/api/v1/apps/{app_id}"
    schema = {
        "type": "object",
        "required": ["sku"],
        "properties": {"sku": {"type": "string"}, "qty": {"type": "integer", "minimum": 1}},
    }
    bad_schema = await api.post(
        f"{base}/event-types",
        json={"name": "order.created", "payload_schema": {"type": "nonsense"}},
        headers=owner,
    )
    assert bad_schema.status_code == 422
    await api.post(
        f"{base}/event-types",
        json={"name": "order.created", "payload_schema": schema},
        headers=owner,
    )
    endpoint = await api.post(
        f"{base}/endpoints", json={"url": "https://hooks.example.com/orders"}, headers=owner
    )
    endpoint_id = endpoint.json()["id"]

    invalid = await api.post(
        f"{base}/messages",
        json={"event_type": "order.created", "payload": {"qty": 0}},
        headers=owner,
    )
    assert invalid.status_code == 422
    assert {d["path"] for d in invalid.json()["error"]["details"]} == {"/", "/qty"}

    for n in range(5):
        response = await api.post(
            f"{base}/messages",
            json={"event_type": "order.created", "payload": {"sku": f"sku-{n}", "qty": 1}},
            headers={**owner, "idempotency-key": f"order-{n}"},
        )
        assert response.status_code == 202

    page_one = (await api.get(f"{base}/messages?limit=3", headers=owner)).json()
    assert len(page_one["data"]) == 3
    page_two = (
        await api.get(f"{base}/messages?limit=3&before={page_one['next_cursor']}", headers=owner)
    ).json()
    assert len(page_two["data"]) == 2 and page_two["next_cursor"] is None
    assert [m["payload"]["sku"] for m in page_one["data"] + page_two["data"]] == [
        f"sku-{n}" for n in reversed(range(5))
    ]

    await dispatcher.run_until_idle()

    log = (await api.get(f"{base}/attempts?endpoint_id={endpoint_id}", headers=owner)).json()
    assert len(log["data"]) == 5
    assert log["data"][0]["delivery_status"] == "succeeded"

    for resource in ("deliveries", "attempts"):
        first = (await api.get(f"{base}/{resource}?limit=2", headers=owner)).json()
        assert len(first["data"]) == 2 and first["next_cursor"] == first["data"][-1]["id"]
        rest = (
            await api.get(
                f"{base}/{resource}?limit=10&before={first['next_cursor']}", headers=owner
            )
        ).json()
        assert len(rest["data"]) == 3 and rest["next_cursor"] is None

    delivery_id = log["data"][0]["delivery_id"]
    detail = (await api.get(f"{base}/deliveries/{delivery_id}", headers=owner)).json()
    assert detail["attempts"][0]["status_code"] == 200
    assert detail["payload"]["qty"] == 1

    stats = (await api.get(f"{base}/endpoints/{endpoint_id}/stats?window=1h", headers=owner)).json()
    assert stats["total"] == 5
    assert stats["success_rate"] == 1.0
    assert stats["p95_ms"] is not None
    assert sum(bucket["total"] for bucket in stats["series"]) == 5

    overview = (await api.get(f"{base}/stats?window=24h", headers=owner)).json()
    assert overview["messages"] == 5
    assert overview["endpoints"] == {
        "total": 1,
        "healthy": 1,
        "degraded": 0,
        "open": 0,
        "disabled": 0,
    }

    secret = (await api.get(f"{base}/endpoints/{endpoint_id}/secret", headers=owner)).json()
    rotated = (
        await api.post(f"{base}/endpoints/{endpoint_id}/secret/rotate", json={}, headers=owner)
    ).json()
    assert rotated["previous"][0]["secret"] == secret["current"]["secret"]
    assert rotated["current"]["secret"] != secret["current"]["secret"]


async def test_api_keys_stop_working_once_expired(api: httpx.AsyncClient, clock: FakeClock) -> None:
    owner = await _signup(api, "keys@acme.dev")
    app_id = await _app(api, owner)
    created = await api.post(
        "/api/v1/api-keys",
        json={"name": "ci", "scopes": ["apps:read"], "expires_in_days": 1},
        headers=owner,
    )
    key = {"authorization": f"Bearer {created.json()['key']}"}
    assert (await api.get(f"/api/v1/apps/{app_id}", headers=key)).status_code == 200

    clock.advance(days=1, seconds=1)
    expired = await api.get(f"/api/v1/apps/{app_id}", headers=key)
    assert expired.status_code == 401
    assert expired.json()["error"]["message"] == "API key has expired"


async def test_login_is_throttled_per_account(api: httpx.AsyncClient, settings: Settings) -> None:
    await _signup(api, "target@acme.dev")
    attempts = int(settings.login_attempts_per_minute)
    for _ in range(attempts):
        response = await api.post(
            "/api/v1/auth/login", json={"email": "target@acme.dev", "password": "guess-guess"}
        )
        assert response.status_code == 401
    blocked = await api.post(
        "/api/v1/auth/login", json={"email": "target@acme.dev", "password": PASSWORD}
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) >= 1


async def test_endpoint_input_is_checked_against_the_registry_and_reserved_headers(
    api: httpx.AsyncClient,
) -> None:
    owner = await _signup(api, "hooks@acme.dev")
    app_id = await _app(api, owner)
    base = f"/api/v1/apps/{app_id}"
    await api.post(f"{base}/event-types", json={"name": "order.created"}, headers=owner)

    unknown = await api.post(
        f"{base}/endpoints",
        json={"url": "https://x.example.com", "event_types": ["order.created", "order.typo"]},
        headers=owner,
    )
    assert unknown.status_code == 422
    assert "order.typo" in unknown.json()["error"]["details"][0]["message"]

    smuggled = await api.post(
        f"{base}/endpoints",
        json={"url": "https://x.example.com", "headers": {"Transfer-Encoding": "chunked"}},
        headers=owner,
    )
    assert smuggled.status_code == 422

    named = await api.post(
        f"{base}/endpoints",
        json={"url": "https://x.example.com", "name": "Orders", "headers": {"x-team": "ops"}},
        headers=owner,
    )
    assert named.status_code == 201
    assert named.json()["name"] == "Orders"

    redos = await api.post(
        f"{base}/event-types",
        json={
            "name": "user.created",
            "payload_schema": {"properties": {"email": {"type": "string", "pattern": "^(a+)+$"}}},
        },
        headers=owner,
    )
    assert redos.status_code == 422
    assert redos.json()["error"]["details"][0]["path"] == "/properties/email/pattern"

    duplicate = await api.post("/api/v1/apps", json={"name": "Billing"}, headers=owner)
    assert duplicate.status_code == 409


async def test_sse_stream_over_real_http(settings: Settings, clock: FakeClock) -> None:
    app = create_app(settings, clock)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )
    serving = asyncio.create_task(server.serve())
    try:
        while not server.started:  # noqa: ASYNC110 - uvicorn has no startup event to await
            await asyncio.sleep(0.02)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            owner = await _signup(client, "live@acme.dev")
            app_id = await _app(client, owner)
            await client.post(
                f"/api/v1/apps/{app_id}/event-types", json={"name": "ping"}, headers=owner
            )
            async with client.stream(
                "GET", f"/api/v1/apps/{app_id}/stream", headers=owner
            ) as stream:
                assert stream.status_code == 200
                assert stream.headers["content-type"].startswith("text/event-stream")
                lines = stream.aiter_lines()
                assert await _next_event(lines) == ("ready", "{}")
                published = await client.post(
                    f"/api/v1/apps/{app_id}/messages",
                    json={"event_type": "ping", "payload": {"n": 1}},
                    headers=owner,
                )
                kind, data = await asyncio.wait_for(_next_event(lines), timeout=5)
                assert kind == "message"
                assert json.loads(data)["id"] == published.json()["id"]
    finally:
        server.should_exit = True
        await serving


async def _next_event(lines: AsyncIterator[str]) -> tuple[str, str]:
    kind = data = ""
    async for line in lines:
        if line.startswith("event:"):
            kind = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data = line.removeprefix("data:").strip()
        elif not line and kind:
            return kind, data
    raise AssertionError("stream ended")
