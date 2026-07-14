import random
from datetime import UTC, datetime, timedelta

import pytest

from relay.domain.retry import (
    RetryPolicy,
    backoff_ceiling,
    backoff_delay,
    parse_retry_after,
    schedule_after_failure,
)

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
POLICY = RetryPolicy(base_seconds=5, max_backoff_seconds=600, max_attempts=6)


@pytest.mark.parametrize(
    ("attempt", "ceiling"), [(1, 5), (2, 10), (3, 20), (4, 40), (7, 320), (8, 600), (40, 600)]
)
def test_ceiling_doubles_until_capped(attempt: int, ceiling: float) -> None:
    assert backoff_ceiling(POLICY, attempt) == ceiling


def test_full_jitter_stays_inside_window_and_actually_varies() -> None:
    rng = random.Random(7)
    delays = [backoff_delay(POLICY, 4, rng=rng) for _ in range(500)]
    assert all(0 <= d <= 40 for d in delays)
    assert max(delays) - min(delays) > 20


def test_retry_after_acts_as_a_floor_but_is_capped() -> None:
    rng = random.Random(1)
    assert backoff_delay(POLICY, 1, retry_after=120, rng=rng) == 120
    capped = RetryPolicy(retry_after_cap_seconds=60)
    assert backoff_delay(capped, 1, retry_after=10_000, rng=rng) == 60


def test_parse_retry_after_seconds_and_http_date() -> None:
    assert parse_retry_after("30", NOW) == 30
    http_date = "Sun, 01 Mar 2026 12:02:00 GMT"
    assert parse_retry_after(http_date, NOW) == 120
    assert parse_retry_after("Sun, 01 Mar 2026 11:00:00 GMT", NOW) == 0
    assert parse_retry_after("soon", NOW) is None
    assert parse_retry_after(None, NOW) is None


def test_schedule_marks_dead_after_max_attempts() -> None:
    rng = random.Random(3)
    decision = schedule_after_failure(POLICY, 5, NOW, rng=rng)
    assert not decision.dead
    assert decision.next_attempt_at is not None
    assert NOW <= decision.next_attempt_at <= NOW + timedelta(seconds=80)

    final = schedule_after_failure(POLICY, 6, NOW, rng=rng)
    assert final.dead
    assert final.next_attempt_at is None
