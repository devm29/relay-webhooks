"""Rate limiting as a generic cell rate algorithm (GCRA).

GCRA is a token bucket expressed as a single timestamp, the theoretical arrival time
(TAT) of the next request, which makes it cheap to keep in a Postgres row and update
under a row lock from any number of dispatcher processes.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class Pace:
    rate_per_second: float
    burst_size: float | None = None

    @property
    def burst(self) -> float:
        """Requests allowed back to back after idling; one second's worth by default."""
        return self.burst_size if self.burst_size is not None else max(self.rate_per_second, 1.0)

    @property
    def interval(self) -> timedelta:
        return timedelta(seconds=1 / self.rate_per_second)

    @property
    def tolerance(self) -> timedelta:
        return self.interval * (self.burst - 1)

    def ready_at(self, tat: datetime | None) -> datetime | None:
        return None if tat is None else tat - self.tolerance


@dataclass(frozen=True, slots=True)
class Grant:
    admitted: int
    tat: datetime | None
    retry_at: datetime | None


def take(pace: Pace, tat: datetime | None, now: datetime, wanted: int = 1) -> Grant:
    """Admit up to ``wanted`` requests at ``now`` and return the new TAT."""
    cursor = tat if tat is not None and tat > now else now
    admitted = 0
    while admitted < wanted and cursor - pace.tolerance <= now:
        cursor += pace.interval
        admitted += 1
    retry_at = None if admitted == wanted else cursor - pace.tolerance
    return Grant(admitted=admitted, tat=cursor if admitted else tat, retry_at=retry_at)
