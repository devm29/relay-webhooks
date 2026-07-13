"""In-process brute-force throttle for the credential endpoints.

Keys are client addresses and email addresses, so both a single source hammering many
accounts and a distributed attack on one account are slowed down. State lives in memory:
behind several API replicas each one throttles independently, which still bounds the
attempt rate to a small multiple of the configured limit.
"""

import math
from collections import OrderedDict
from datetime import datetime

from relay.domain.errors import TooManyRequestsError
from relay.domain.pacing import Pace, take

_MAX_KEYS = 50_000


def _per_minute(attempts: float) -> Pace:
    return Pace(rate_per_second=attempts / 60, burst_size=attempts)


class LoginThrottle:
    """Accounts get a tight budget; client addresses a looser one, since many people can
    share an address (an office NAT, or the console's own server-side proxy)."""

    def __init__(self, *, per_account: float, per_client: float, max_keys: int = _MAX_KEYS) -> None:
        self._account = _per_minute(per_account)
        self._client = _per_minute(per_client)
        self._tats: OrderedDict[str, datetime] = OrderedDict()
        self._max_keys = max_keys

    def check_login(self, client: str, email: str, now: datetime) -> None:
        self._check({f"ip:{client}": self._client, f"email:{email.lower()}": self._account}, now)

    def check_signup(self, client: str, now: datetime) -> None:
        self._check({f"ip:{client}": self._client}, now)

    def _check(self, keys: dict[str, Pace], now: datetime) -> None:
        """Take one attempt from every key, or raise without consuming any of them."""
        grants = {key: take(pace, self._tat(key, now), now) for key, pace in keys.items()}
        blocked = [g.retry_at for g in grants.values() if g.retry_at is not None]
        if blocked:
            wait = max(blocked) - now
            raise TooManyRequestsError(
                "too many sign-in attempts; try again shortly",
                retry_after_seconds=max(1, math.ceil(wait.total_seconds())),
            )
        for key, grant in grants.items():
            if grant.tat is not None:
                self._tats[key] = grant.tat
                self._tats.move_to_end(key)
        while len(self._tats) > self._max_keys:
            self._tats.popitem(last=False)

    def _tat(self, key: str, now: datetime) -> datetime | None:
        tat = self._tats.get(key)
        if tat is not None and tat <= now:
            del self._tats[key]
            return None
        return tat
