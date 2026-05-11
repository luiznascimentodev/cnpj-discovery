"""Host policy: circuit breaker, EWMA latency, adaptive throttle, budget.

All decisions are persisted in `paid_enrichment.crawl_hosts` so they survive
worker restarts. Redis is not required — Postgres is the source of truth.

Circuit states:
  closed    — normal operation.
  open      — no requests until circuit_opened_at + OPEN_DURATION_SECONDS.
  half_open — one test request allowed to probe recovery.

Budget:
  crawl_budget_per_day / crawl_budget_used / crawl_budget_date are reset daily.
  Workers check budget before claiming, but budget enforcement is best-effort
  (at-least-once semantics; exact enforcement needs a Postgres advisory lock or
  Redis counter, which can be added as an optional layer later).

EWMA latency:
  latency_ewma_ms = alpha * new_sample + (1 - alpha) * old_ewma
  EWMA_ALPHA = 0.2 gives a smoothed window over ~5 samples.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

EWMA_ALPHA = 0.2
OPEN_DURATION_SECONDS = 600  # 10 minutes per open state
HALF_OPEN_TEST_DELAY_SECONDS = 30
BLOCK_AFTER_CONSECUTIVE_FAILURES = 5
BLOCK_AFTER_CONSECUTIVE_4XX = 3
DEFAULT_MIN_DELAY_SECONDS = 1.0
DEFAULT_MAX_CONCURRENCY = 1
RETRY_BASE_SECONDS = 60
RETRY_MAX_SECONDS = 3600

_SQL_GET_HOST_POLICY = """
    SELECT
        consecutive_failures,
        blocked_until,
        last_fetch_at,
        crawl_delay_seconds,
        min_delay_seconds,
        max_concurrency,
        latency_ewma_ms,
        last_http_status,
        last_retry_after_at,
        circuit_state,
        circuit_opened_at,
        crawl_budget_per_day,
        crawl_budget_used,
        crawl_budget_date
    FROM paid_enrichment.crawl_hosts
    WHERE domain = $1
"""

_SQL_UPSERT_HOST_POLICY = """
    INSERT INTO paid_enrichment.crawl_hosts (
        domain, consecutive_failures, blocked_until, last_fetch_at,
        min_delay_seconds, max_concurrency,
        latency_ewma_ms, last_http_status, last_retry_after_at,
        circuit_state, circuit_opened_at,
        crawl_budget_per_day, crawl_budget_used, crawl_budget_date
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, COALESCE($14, current_date))
    ON CONFLICT (domain) DO UPDATE SET
        consecutive_failures = EXCLUDED.consecutive_failures,
        blocked_until        = EXCLUDED.blocked_until,
        last_fetch_at        = EXCLUDED.last_fetch_at,
        min_delay_seconds    = EXCLUDED.min_delay_seconds,
        max_concurrency      = EXCLUDED.max_concurrency,
        latency_ewma_ms      = EXCLUDED.latency_ewma_ms,
        last_http_status     = EXCLUDED.last_http_status,
        last_retry_after_at  = EXCLUDED.last_retry_after_at,
        circuit_state        = EXCLUDED.circuit_state,
        circuit_opened_at    = EXCLUDED.circuit_opened_at,
        crawl_budget_per_day = EXCLUDED.crawl_budget_per_day,
        crawl_budget_used    = EXCLUDED.crawl_budget_used,
        crawl_budget_date    = COALESCE(EXCLUDED.crawl_budget_date, current_date)
"""

_SQL_INCREMENT_BUDGET = """
    INSERT INTO paid_enrichment.crawl_hosts (
        domain, crawl_budget_used, crawl_budget_date
    )
    VALUES ($1, 1, current_date)
    ON CONFLICT (domain) DO UPDATE SET
        crawl_budget_used = CASE
            WHEN paid_enrichment.crawl_hosts.crawl_budget_date = current_date
            THEN paid_enrichment.crawl_hosts.crawl_budget_used + 1
            ELSE 1
        END,
        crawl_budget_date = current_date
"""


@dataclass
class HostPolicy:
    domain: str
    consecutive_failures: int = 0
    blocked_until: Optional[datetime] = None
    last_fetch_at: Optional[datetime] = None
    crawl_delay_seconds: Optional[float] = None
    min_delay_seconds: float = DEFAULT_MIN_DELAY_SECONDS
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    latency_ewma_ms: Optional[int] = None
    last_http_status: Optional[int] = None
    last_retry_after_at: Optional[datetime] = None
    circuit_state: str = "closed"
    circuit_opened_at: Optional[datetime] = None
    crawl_budget_per_day: int = 25
    crawl_budget_used: int = 0
    crawl_budget_date: Optional[object] = None

    @property
    def budget_exhausted(self) -> bool:
        from datetime import date
        today = date.today()
        if self.crawl_budget_date and self.crawl_budget_date != today:
            return False
        return self.crawl_budget_used >= self.crawl_budget_per_day

    def effective_circuit_state(self) -> str:
        if self.circuit_state != "open":
            return self.circuit_state
        if self.circuit_opened_at is None:
            return "closed"
        now = datetime.now(timezone.utc)
        elapsed = (now - self.circuit_opened_at).total_seconds()
        if elapsed >= OPEN_DURATION_SECONDS:
            return "half_open"
        return "open"

    def is_blocked(self) -> bool:
        """True when request should not be attempted now."""
        state = self.effective_circuit_state()
        if state == "open":
            return True
        now = datetime.now(timezone.utc)
        if self.blocked_until and self.blocked_until > now:
            return True
        return False

    def suggested_delay_seconds(self) -> float:
        """Adaptive delay: max(robots_delay, min_delay, ewma/target_concurrency)."""
        delays = [self.min_delay_seconds]
        if self.crawl_delay_seconds and self.crawl_delay_seconds > 0:
            delays.append(self.crawl_delay_seconds)
        if self.latency_ewma_ms and self.max_concurrency > 0:
            ewma_based = (self.latency_ewma_ms / 1000.0) / self.max_concurrency
            delays.append(ewma_based)
        return max(delays)

    def update_ewma(self, latency_ms: int) -> "HostPolicy":
        """Return a new HostPolicy with updated EWMA latency (does not mutate)."""
        if self.latency_ewma_ms is None:
            new_ewma = latency_ms
        else:
            new_ewma = int(EWMA_ALPHA * latency_ms + (1 - EWMA_ALPHA) * self.latency_ewma_ms)
        import dataclasses
        return dataclasses.replace(self, latency_ewma_ms=new_ewma)

    def open_circuit(self) -> "HostPolicy":
        import dataclasses
        return dataclasses.replace(
            self,
            circuit_state="open",
            circuit_opened_at=datetime.now(timezone.utc),
        )

    def close_circuit(self) -> "HostPolicy":
        import dataclasses
        return dataclasses.replace(
            self,
            circuit_state="closed",
            circuit_opened_at=None,
            consecutive_failures=0,
            blocked_until=None,
        )

    def register_failure(
        self,
        *,
        http_status: Optional[int] = None,
        retry_after_seconds: Optional[int] = None,
    ) -> "HostPolicy":
        """Return updated policy after a failed request. Never decreases delay."""
        import dataclasses
        now = datetime.now(timezone.utc)
        failures = self.consecutive_failures + 1
        blocked_until = self.blocked_until

        if retry_after_seconds is not None and retry_after_seconds > 0:
            retry_after_at = now + timedelta(seconds=retry_after_seconds)
            blocked_until = retry_after_at
            last_retry_after_at = now
        else:
            last_retry_after_at = self.last_retry_after_at

        circuit_state = self.circuit_state
        circuit_opened_at = self.circuit_opened_at
        if failures >= BLOCK_AFTER_CONSECUTIVE_FAILURES:
            circuit_state = "open"
            circuit_opened_at = circuit_opened_at or now
            if blocked_until is None:
                blocked_until = now + timedelta(seconds=OPEN_DURATION_SECONDS)

        return dataclasses.replace(
            self,
            consecutive_failures=failures,
            blocked_until=blocked_until,
            last_fetch_at=now,
            last_http_status=http_status,
            last_retry_after_at=last_retry_after_at,
            circuit_state=circuit_state,
            circuit_opened_at=circuit_opened_at,
        )

    def register_success(self, latency_ms: int) -> "HostPolicy":
        import dataclasses
        updated = self.update_ewma(latency_ms)
        return dataclasses.replace(
            updated,
            consecutive_failures=0,
            blocked_until=None,
            last_fetch_at=datetime.now(timezone.utc),
            circuit_state="closed",
            circuit_opened_at=None,
        )


def jittered_retry_delay(attempts: int) -> int:
    raw = RETRY_BASE_SECONDS * (2 ** max(attempts - 1, 0))
    jittered = raw * random.uniform(0.8, 1.2)
    return int(min(jittered, RETRY_MAX_SECONDS))


async def get_host_policy(pool, domain: str) -> HostPolicy:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SQL_GET_HOST_POLICY, domain)
    if not row:
        return HostPolicy(domain=domain)
    return HostPolicy(
        domain=domain,
        consecutive_failures=row["consecutive_failures"] or 0,
        blocked_until=row["blocked_until"],
        last_fetch_at=row["last_fetch_at"],
        crawl_delay_seconds=(
            float(row["crawl_delay_seconds"]) if row["crawl_delay_seconds"] is not None else None
        ),
        min_delay_seconds=float(row["min_delay_seconds"]) if row["min_delay_seconds"] is not None else DEFAULT_MIN_DELAY_SECONDS,
        max_concurrency=row["max_concurrency"] if row["max_concurrency"] is not None else DEFAULT_MAX_CONCURRENCY,
        latency_ewma_ms=row["latency_ewma_ms"],
        last_http_status=row["last_http_status"],
        last_retry_after_at=row["last_retry_after_at"],
        circuit_state=row["circuit_state"] or "closed",
        circuit_opened_at=row["circuit_opened_at"],
        crawl_budget_per_day=row["crawl_budget_per_day"] if row["crawl_budget_per_day"] is not None else 25,
        crawl_budget_used=row["crawl_budget_used"] if row["crawl_budget_used"] is not None else 0,
        crawl_budget_date=row["crawl_budget_date"],
    )


async def save_host_policy(pool, policy: HostPolicy) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_UPSERT_HOST_POLICY,
            policy.domain,
            policy.consecutive_failures,
            policy.blocked_until,
            policy.last_fetch_at,
            policy.min_delay_seconds,
            policy.max_concurrency,
            policy.latency_ewma_ms,
            policy.last_http_status,
            policy.last_retry_after_at,
            policy.circuit_state,
            policy.circuit_opened_at,
            policy.crawl_budget_per_day,
            policy.crawl_budget_used,
            policy.crawl_budget_date,
        )


async def increment_host_budget(pool, domain: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_SQL_INCREMENT_BUDGET, domain)
