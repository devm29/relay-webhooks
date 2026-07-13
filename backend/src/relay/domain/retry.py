"""Retry scheduling: exponential backoff with full jitter, bounded by Retry-After hints."""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

_default_rng = random.Random()


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    base_seconds: float = 5.0
    max_backoff_seconds: float = 3600.0
    max_attempts: int = 8
    retry_after_cap_seconds: float = 3600.0


def backoff_ceiling(policy: RetryPolicy, attempt: int) -> float:
    """Upper bound of the jitter window after the given (1-based) failed attempt."""
    exponent = min(max(attempt - 1, 0), 32)
    return min(policy.max_backoff_seconds, policy.base_seconds * (1 << exponent))


def backoff_delay(
    policy: RetryPolicy,
    attempt: int,
    *,
    retry_after: float | None = None,
    rng: random.Random | None = None,
) -> float:
    ceiling = backoff_ceiling(policy, attempt)
    jittered = (rng or _default_rng).uniform(0, ceiling)
    if retry_after is None:
        return jittered
    return max(jittered, min(retry_after, policy.retry_after_cap_seconds))


def parse_retry_after(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - now).total_seconds(), 0.0)


@dataclass(frozen=True, slots=True)
class RetryDecision:
    dead: bool
    next_attempt_at: datetime | None


def schedule_after_failure(
    policy: RetryPolicy,
    attempt: int,
    now: datetime,
    *,
    retry_after: float | None = None,
    rng: random.Random | None = None,
) -> RetryDecision:
    if attempt >= policy.max_attempts:
        return RetryDecision(dead=True, next_attempt_at=None)
    delay = backoff_delay(policy, attempt, retry_after=retry_after, rng=rng)
    return RetryDecision(dead=False, next_attempt_at=now + timedelta(seconds=delay))
