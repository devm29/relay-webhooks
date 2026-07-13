from datetime import UTC, datetime, timedelta

import pytest

from relay.auth.throttle import LoginThrottle
from relay.domain.errors import TooManyRequestsError

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def test_account_budget_is_tighter_than_the_client_budget() -> None:
    throttle = LoginThrottle(per_account=3, per_client=10)
    for _ in range(3):
        throttle.check_login("10.0.0.1", "Ann@acme.dev", NOW)
    with pytest.raises(TooManyRequestsError) as blocked:
        throttle.check_login("10.0.0.2", "ann@acme.dev", NOW)
    assert blocked.value.retry_after_seconds >= 1
    throttle.check_login("10.0.0.1", "bob@acme.dev", NOW)


def test_a_rejected_attempt_consumes_nothing_and_budget_refills() -> None:
    throttle = LoginThrottle(per_account=1, per_client=1)
    throttle.check_login("10.0.0.1", "ann@acme.dev", NOW)
    with pytest.raises(TooManyRequestsError):
        throttle.check_login("10.0.0.1", "bob@acme.dev", NOW)
    throttle.check_login("10.0.0.2", "bob@acme.dev", NOW)
    throttle.check_login("10.0.0.1", "ann@acme.dev", NOW + timedelta(minutes=1))
