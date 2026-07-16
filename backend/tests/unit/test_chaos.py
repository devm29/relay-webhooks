import json
import time

import httpx
import pytest

from relay.chaos.app import create_chaos_app
from relay.signing import generate_secret, signature_headers

SECRET = generate_secret()
BODY = json.dumps({"type": "order.created", "data": {"id": 1}}).encode()


def _client(verify_secret: str | None = None) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=create_chaos_app(verify_secret))
    return httpx.AsyncClient(transport=transport, base_url="http://chaos")


def _signed(secret: str = SECRET) -> dict[str, str]:
    return signature_headers([secret], "msg_1", int(time.time()), BODY)


async def test_healthy_receiver_accepts_and_records_a_valid_signature() -> None:
    async with _client(SECRET) as chaos:
        response = await chaos.post("/hooks/orders", content=BODY, headers=_signed())
        assert response.status_code == 200
        [received] = (await chaos.get("/inbox")).json()
    assert received["receiver"] == "orders"
    assert received["signature"] == "valid"
    assert received["event_type"] == "order.created"
    assert received["webhook_id"] == "msg_1"


async def test_bad_signature_is_rejected_with_401() -> None:
    async with _client(SECRET) as chaos:
        response = await chaos.post(
            "/hooks/orders", content=BODY, headers=_signed(generate_secret())
        )
    assert response.status_code == 401


async def test_failure_scenario_comes_from_the_query_string_with_retry_after() -> None:
    async with _client() as chaos:
        response = await chaos.post(
            "/hooks/flaky",
            params={"fail_rate": 1, "fail_status": 503, "retry_after": 7},
            content=BODY,
        )
    assert response.status_code == 503
    assert response.headers["retry-after"] == "7"


async def test_control_override_beats_the_query_string_until_cleared() -> None:
    async with _client() as chaos:
        await chaos.put("/control/scenarios/billing", json={"gone": True})
        assert (await chaos.post("/hooks/billing", content=BODY)).status_code == 410
        assert (await chaos.post("/hooks/other", content=BODY)).status_code == 200

        await chaos.delete("/control/scenarios/billing")
        assert (await chaos.post("/hooks/billing", content=BODY)).status_code == 200
        assert (await chaos.get("/control/scenarios")).json() == {}


@pytest.mark.parametrize("rate", [-0.1, 1.5])
async def test_out_of_range_scenarios_are_rejected(rate: float) -> None:
    async with _client() as chaos:
        response = await chaos.post("/hooks/x", params={"fail_rate": rate}, content=BODY)
    assert response.status_code == 422
