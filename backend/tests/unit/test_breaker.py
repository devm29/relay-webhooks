from datetime import UTC, datetime, timedelta

from relay.domain.breaker import (
    BreakerPolicy,
    BreakerSnapshot,
    admit,
    cooldown,
    record_failure,
    record_success,
)
from relay.domain.enums import BreakerState

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
POLICY = BreakerPolicy(
    failure_threshold=3,
    base_cooldown_seconds=30,
    max_cooldown_seconds=120,
    disable_after_trips=3,
    probe_timeout_seconds=10,
)


def _trip(snap: BreakerSnapshot, at: datetime) -> BreakerSnapshot:
    for _ in range(POLICY.failure_threshold):
        snap = record_failure(snap, at, POLICY).snapshot
    return snap


def test_closed_counts_failures_and_opens_at_threshold() -> None:
    snap = BreakerSnapshot()
    snap = record_failure(snap, NOW, POLICY).snapshot
    snap = record_failure(snap, NOW, POLICY).snapshot
    assert snap.state is BreakerState.CLOSED
    assert snap.consecutive_failures == 2

    snap = record_failure(snap, NOW, POLICY).snapshot
    assert snap.state is BreakerState.OPEN
    assert snap.trip_count == 1
    assert snap.open_until == NOW + timedelta(seconds=30)


def test_success_resets_everything() -> None:
    snap = record_failure(BreakerSnapshot(), NOW, POLICY).snapshot
    assert record_success(snap).snapshot == BreakerSnapshot()


def test_open_rejects_until_cooldown_then_admits_a_single_probe() -> None:
    snap = _trip(BreakerSnapshot(), NOW)
    rejected = admit(snap, NOW + timedelta(seconds=5), POLICY)
    assert not rejected.allowed
    assert rejected.retry_at == snap.open_until

    probe = admit(snap, NOW + timedelta(seconds=31), POLICY)
    assert probe.allowed and probe.is_probe
    assert probe.snapshot.state is BreakerState.HALF_OPEN

    second = admit(probe.snapshot, NOW + timedelta(seconds=32), POLICY)
    assert not second.allowed


def test_stale_probe_is_taken_over_after_probe_timeout() -> None:
    probing = admit(_trip(BreakerSnapshot(), NOW), NOW + timedelta(seconds=31), POLICY).snapshot
    takeover = admit(probing, NOW + timedelta(seconds=45), POLICY)
    assert takeover.allowed and takeover.is_probe


def test_failed_probe_reopens_with_longer_cooldown_and_eventually_disables() -> None:
    snap = _trip(BreakerSnapshot(), NOW)
    at = NOW
    disabled = False
    for expected_trip in (2, 3):
        at = snap.open_until or at
        probe = admit(snap, at, POLICY).snapshot
        outcome = record_failure(probe, at, POLICY)
        snap = outcome.snapshot
        assert snap.state is BreakerState.OPEN
        assert snap.trip_count == expected_trip
        assert snap.open_until == at + cooldown(POLICY, expected_trip)
        disabled = outcome.disable_endpoint
    assert disabled


def test_cooldown_is_capped() -> None:
    assert cooldown(POLICY, 1) == timedelta(seconds=30)
    assert cooldown(POLICY, 2) == timedelta(seconds=60)
    assert cooldown(POLICY, 10) == timedelta(seconds=120)


def test_successful_probe_closes() -> None:
    probe = admit(_trip(BreakerSnapshot(), NOW), NOW + timedelta(minutes=1), POLICY).snapshot
    assert record_success(probe).snapshot.state is BreakerState.CLOSED
