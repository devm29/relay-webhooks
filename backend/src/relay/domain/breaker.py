"""Per-endpoint circuit breaker as a pure state machine.

Persisted state is loaded, passed through these functions and written back by the
caller under a row lock, so every dispatcher process sees one consistent breaker.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from relay.domain.enums import BreakerState


@dataclass(frozen=True, slots=True)
class BreakerPolicy:
    failure_threshold: int = 5
    base_cooldown_seconds: float = 30.0
    max_cooldown_seconds: float = 900.0
    disable_after_trips: int = 8
    probe_timeout_seconds: float = 60.0


@dataclass(frozen=True, slots=True)
class BreakerSnapshot:
    state: BreakerState = BreakerState.CLOSED
    consecutive_failures: int = 0
    trip_count: int = 0
    opened_at: datetime | None = None
    open_until: datetime | None = None
    probe_started_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Admission:
    allowed: bool
    snapshot: BreakerSnapshot
    retry_at: datetime | None = None
    is_probe: bool = False


@dataclass(frozen=True, slots=True)
class Outcome:
    snapshot: BreakerSnapshot
    disable_endpoint: bool = False


def cooldown(policy: BreakerPolicy, trip_count: int) -> timedelta:
    exponent = min(max(trip_count - 1, 0), 20)
    seconds = min(policy.max_cooldown_seconds, policy.base_cooldown_seconds * (1 << exponent))
    return timedelta(seconds=seconds)


def admit(snap: BreakerSnapshot, now: datetime, policy: BreakerPolicy) -> Admission:
    match snap.state:
        case BreakerState.CLOSED:
            return Admission(allowed=True, snapshot=snap)
        case BreakerState.OPEN:
            if snap.open_until is not None and now < snap.open_until:
                return Admission(allowed=False, snapshot=snap, retry_at=snap.open_until)
            probing = replace(snap, state=BreakerState.HALF_OPEN, probe_started_at=now)
            return Admission(allowed=True, snapshot=probing, is_probe=True)
        case BreakerState.HALF_OPEN:
            probe_deadline = (
                snap.probe_started_at + timedelta(seconds=policy.probe_timeout_seconds)
                if snap.probe_started_at is not None
                else now
            )
            if now < probe_deadline:
                return Admission(allowed=False, snapshot=snap, retry_at=probe_deadline)
            # The previous probe never reported back (crashed worker); take over as the new probe.
            return Admission(
                allowed=True, snapshot=replace(snap, probe_started_at=now), is_probe=True
            )


def record_success(snap: BreakerSnapshot) -> Outcome:
    del snap
    return Outcome(snapshot=BreakerSnapshot())


def record_failure(snap: BreakerSnapshot, now: datetime, policy: BreakerPolicy) -> Outcome:
    failures = snap.consecutive_failures + 1
    match snap.state:
        case BreakerState.CLOSED if failures < policy.failure_threshold:
            return Outcome(snapshot=replace(snap, consecutive_failures=failures))
        case BreakerState.OPEN:
            return Outcome(snapshot=replace(snap, consecutive_failures=failures))
        case _:
            trips = snap.trip_count + 1
            opened = BreakerSnapshot(
                state=BreakerState.OPEN,
                consecutive_failures=failures,
                trip_count=trips,
                opened_at=now,
                open_until=now + cooldown(policy, trips),
            )
            return Outcome(snapshot=opened, disable_endpoint=trips >= policy.disable_after_trips)
