from datetime import UTC, datetime, timedelta

from relay.domain.pacing import Pace, take

T0 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def test_allows_a_one_second_burst_then_paces() -> None:
    pace = Pace(rate_per_second=2)
    grant = take(pace, None, T0, wanted=5)
    assert grant.admitted == 2
    assert grant.retry_at == T0 + timedelta(seconds=0.5)

    later = take(pace, grant.tat, T0 + timedelta(seconds=0.5))
    assert later.admitted == 1
    assert take(pace, later.tat, T0 + timedelta(seconds=0.5)).admitted == 0


def test_slow_rates_admit_one_at_a_time() -> None:
    pace = Pace(rate_per_second=0.5)
    first = take(pace, None, T0)
    assert first.admitted == 1
    blocked = take(pace, first.tat, T0 + timedelta(seconds=1))
    assert blocked.admitted == 0
    assert blocked.tat == first.tat
    assert blocked.retry_at == T0 + timedelta(seconds=2)
    assert take(pace, first.tat, T0 + timedelta(seconds=2)).admitted == 1


def test_idle_time_does_not_accumulate_beyond_the_burst() -> None:
    pace = Pace(rate_per_second=3)
    stale_tat = T0 - timedelta(hours=1)
    assert take(pace, stale_tat, T0, wanted=10).admitted == 3


def test_ready_at_matches_the_admission_check() -> None:
    pace = Pace(rate_per_second=4)
    grant = take(pace, None, T0, wanted=10)
    ready = pace.ready_at(grant.tat)
    assert ready is not None
    assert take(pace, grant.tat, ready - timedelta(microseconds=1)).admitted == 0
    assert take(pace, grant.tat, ready).admitted == 1


def test_explicit_burst_overrides_the_default() -> None:
    pace = Pace(rate_per_second=10 / 60, burst_size=10)
    grant = take(pace, None, T0, wanted=20)
    assert grant.admitted == 10
    assert grant.retry_at == T0 + timedelta(seconds=6)
