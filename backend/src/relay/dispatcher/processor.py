import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from relay.clock import Clock
from relay.config import Settings
from relay.delivery.client import SendResult, WebhookSender
from relay.domain import breaker
from relay.domain.breaker import BreakerSnapshot
from relay.domain.enums import AttemptOutcome, AttemptTrigger, DeliveryStatus
from relay.domain.models import LiveEvent
from relay.domain.retry import RetryPolicy, parse_retry_after, schedule_after_failure
from relay.events.notify import publish_live
from relay.ids import new_id
from relay.logging import get_logger
from relay.persistence import queue
from relay.persistence.queue import DeliveryJob
from relay.persistence.repositories.catalog import EndpointRepository, read_breaker, write_breaker
from relay.persistence.tables import Attempt
from relay.signing import signature_headers

log = get_logger(__name__)

GONE = 410


@dataclass(frozen=True, slots=True)
class Policies:
    retry: RetryPolicy
    breaker: breaker.BreakerPolicy
    lease_for: timedelta
    default_timeout: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "Policies":
        return cls(
            retry=RetryPolicy(
                base_seconds=settings.retry_base_seconds,
                max_backoff_seconds=settings.retry_max_backoff_seconds,
                max_attempts=settings.retry_max_attempts,
                retry_after_cap_seconds=settings.retry_after_cap_seconds,
            ),
            breaker=breaker.BreakerPolicy(
                failure_threshold=settings.breaker_failure_threshold,
                base_cooldown_seconds=settings.breaker_base_cooldown_seconds,
                max_cooldown_seconds=settings.breaker_max_cooldown_seconds,
                disable_after_trips=settings.breaker_disable_after_trips,
                probe_timeout_seconds=settings.breaker_probe_timeout_seconds,
            ),
            lease_for=timedelta(seconds=settings.dispatcher_lease_seconds),
            default_timeout=settings.delivery_timeout_seconds,
        )


def render_body(job: DeliveryJob) -> bytes:
    envelope = {
        "type": job.event_type,
        "timestamp": job.message_created_at.isoformat(),
        "data": job.payload,
    }
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode()


class DeliveryProcessor:
    """Runs one leased delivery through the breaker, the HTTP call and the bookkeeping
    that follows. Rate limits are already applied when the delivery is leased."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        sender: WebhookSender,
        policies: Policies,
        clock: Clock,
        rng: random.Random | None = None,
    ) -> None:
        self._sessions = sessions
        self._sender = sender
        self._policies = policies
        self._clock = clock
        self._rng = rng or random.Random()

    async def lease(self, limit: int) -> list[DeliveryJob]:
        async with self._sessions() as session, session.begin():
            return await queue.lease_due(
                session,
                now=self._clock.now(),
                lease_for=self._policies.lease_for,
                limit=limit,
                probe_timeout=timedelta(seconds=self._policies.breaker.probe_timeout_seconds),
            )

    async def process(self, job: DeliveryJob) -> None:
        now = self._clock.now()
        admitted = await self._admit(job, now)
        if admitted is None:
            return
        signing_secrets, is_probe = admitted

        body = render_body(job)
        headers = {
            **job.headers,
            **signature_headers(signing_secrets, job.message_id, int(now.timestamp()), body),
            "content-type": "application/json",
        }
        timeout = job.timeout_seconds or self._policies.default_timeout
        result = await self._sender.send(job.endpoint_url, body, headers, timeout=timeout)
        await self._record(job, result, started_at=now, is_probe=is_probe)

    async def _admit(self, job: DeliveryJob, now: datetime) -> tuple[list[str], bool] | None:
        async with self._sessions() as session, session.begin():
            endpoints = EndpointRepository(session)
            current = await endpoints.breaker_snapshot(job.endpoint_id)
            admission = breaker.admit(current, now, self._policies.breaker)
            # Only the open -> half-open hand-off writes here; a closed breaker costs one read.
            if (
                admission.allowed
                and admission.snapshot != current
                and not await endpoints.transition_breaker(
                    job.endpoint_id, current, admission.snapshot, now
                )
            ):
                admission = breaker.Admission(
                    allowed=False, snapshot=current, retry_at=now + timedelta(seconds=1)
                )
            if not admission.allowed:
                retry_at = admission.retry_at or now + timedelta(seconds=1)
                await queue.release(session, job, retry_at=retry_at, now=now)
                return None
            secrets = [s.secret for s in await endpoints.active_secrets(job.endpoint_id, now)]
        return secrets, admission.is_probe

    def _judge(
        self, job: DeliveryJob, result: SendResult, finished: datetime
    ) -> tuple[str | None, datetime | None, str | None]:
        """Error text, next attempt time (None means dead) and a reason to disable."""
        if result.ok:
            return None, None, None
        error = result.error
        if result.status_code == GONE:
            reason = "endpoint responded 410 Gone"
            return error or reason, None, reason
        decision = schedule_after_failure(
            self._policies.retry,
            job.schedule_index + 1,
            finished,
            retry_after=parse_retry_after(result.retry_after, finished),
            rng=self._rng,
        )
        if error is None and result.status_code is not None:
            error = f"HTTP {result.status_code}"
        return error, decision.next_attempt_at, None

    async def _record(
        self, job: DeliveryJob, result: SendResult, *, started_at: datetime, is_probe: bool
    ) -> None:
        finished = self._clock.now()
        attempt_number = job.attempt_count + 1
        error, next_attempt_at, disable_reason = self._judge(job, result, finished)

        attempt_id = new_id("atm")
        async with self._sessions() as session, session.begin():
            session.add(
                Attempt(
                    id=attempt_id,
                    app_id=job.app_id,
                    delivery_id=job.delivery_id,
                    message_id=job.message_id,
                    endpoint_id=job.endpoint_id,
                    attempt_number=attempt_number,
                    trigger=(
                        AttemptTrigger.REPLAY if job.replay else AttemptTrigger.SCHEDULED
                    ).value,
                    outcome=(
                        AttemptOutcome.SUCCEEDED if result.ok else AttemptOutcome.FAILED
                    ).value,
                    status_code=result.status_code,
                    error=error,
                    response_snippet=result.response_snippet,
                    latency_ms=result.latency_ms,
                    started_at=started_at,
                    next_attempt_at=next_attempt_at,
                )
            )

            if result.ok:
                assert result.status_code is not None
                owned = await queue.mark_succeeded(
                    session, job, status_code=result.status_code, now=finished
                )
                delivery_status = DeliveryStatus.SUCCEEDED
            else:
                owned = await queue.mark_failed(
                    session,
                    job,
                    status_code=result.status_code,
                    error=error,
                    next_attempt_at=next_attempt_at,
                    now=finished,
                )
                delivery_status = (
                    DeliveryStatus.PENDING if next_attempt_at is not None else DeliveryStatus.DEAD
                )
            if not owned:
                # Another worker re-leased this delivery after our lease lapsed. The attempt
                # stays in the audit trail, but its result must not drive the breaker or the
                # delivery state that now belongs to the new owner.
                log.warning("delivery.lease_lost", delivery_id=job.delivery_id)
                return

            endpoints = EndpointRepository(session)
            if result.ok:
                await endpoints.close_breaker(job.endpoint_id, finished)
                outcome = breaker.record_success(BreakerSnapshot())
            else:
                row = await endpoints.lock_breaker(job.endpoint_id)
                snapshot = read_breaker(row)
                outcome = breaker.record_failure(snapshot, finished, self._policies.breaker)
                if outcome.snapshot != snapshot:
                    write_breaker(row, outcome.snapshot, finished)

            if outcome.disable_endpoint and disable_reason is None:
                disable_reason = (
                    f"circuit breaker opened {outcome.snapshot.trip_count} times in a row"
                )
            if disable_reason is not None:
                await endpoints.disable(job.endpoint_id, disable_reason, finished)
                log.warning("endpoint.disabled", endpoint_id=job.endpoint_id, reason=disable_reason)
            elif result.ok and is_probe:
                await queue.resume_endpoint(session, job.endpoint_id, finished)

            await publish_live(
                session,
                LiveEvent(
                    kind="attempt",
                    app_id=job.app_id,
                    id=attempt_id,
                    message_id=job.message_id,
                    event_type=job.event_type,
                    endpoint_id=job.endpoint_id,
                    delivery_id=job.delivery_id,
                    outcome=AttemptOutcome.SUCCEEDED if result.ok else AttemptOutcome.FAILED,
                    status_code=result.status_code,
                    latency_ms=result.latency_ms,
                    attempt_number=attempt_number,
                    delivery_status=delivery_status,
                    at=finished,
                ),
            )

        log.info(
            "delivery.attempt",
            delivery_id=job.delivery_id,
            endpoint_id=job.endpoint_id,
            attempt=attempt_number,
            status=result.status_code,
            ok=result.ok,
            latency_ms=result.latency_ms,
            next_attempt_at=next_attempt_at.isoformat() if next_attempt_at else None,
        )
