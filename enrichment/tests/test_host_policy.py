from datetime import date, datetime, timedelta, timezone

import pytest

from crawler.host_policy import (
    BLOCK_AFTER_CONSECUTIVE_FAILURES,
    EWMA_ALPHA,
    OPEN_DURATION_SECONDS,
    HostPolicy,
    get_host_policy,
    increment_host_budget,
    jittered_retry_delay,
    save_host_policy,
)


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


class FakeConnection:
    def __init__(self, fetchrow_result=None):
        self._fetchrow_result = fetchrow_result
        self.execute_calls = []

    async def fetchrow(self, query, *args):
        return self._fetchrow_result

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


class TestJitteredRetryDelay:
    def test_within_jitter_band(self):
        for _ in range(30):
            d = jittered_retry_delay(1)
            assert 48 <= d <= 72

    def test_capped_at_max(self):
        for _ in range(20):
            assert jittered_retry_delay(30) <= 3600


class TestHostPolicyDefaults:
    def test_new_policy_is_closed(self):
        p = HostPolicy(domain="acme.com.br")
        assert p.circuit_state == "closed"
        assert not p.is_blocked()

    def test_budget_exhausted_today(self):
        p = HostPolicy(
            domain="x.com",
            crawl_budget_per_day=5,
            crawl_budget_used=5,
            crawl_budget_date=date.today(),
        )
        assert p.budget_exhausted

    def test_budget_not_exhausted_different_day(self):
        yesterday = date.today() - timedelta(days=1)
        p = HostPolicy(
            domain="x.com",
            crawl_budget_per_day=5,
            crawl_budget_used=100,
            crawl_budget_date=yesterday,
        )
        assert not p.budget_exhausted

    def test_budget_not_exhausted_below_limit(self):
        p = HostPolicy(
            domain="x.com",
            crawl_budget_per_day=25,
            crawl_budget_used=10,
            crawl_budget_date=date.today(),
        )
        assert not p.budget_exhausted


class TestCircuitBreaker:
    def test_open_circuit_blocks(self):
        p = HostPolicy(domain="x.com").open_circuit()
        assert p.circuit_state == "open"
        assert p.is_blocked()

    def test_closed_circuit_not_blocked(self):
        p = HostPolicy(domain="x.com")
        assert not p.is_blocked()

    def test_circuit_transitions_to_half_open_after_duration(self):
        opened_long_ago = datetime.now(timezone.utc) - timedelta(seconds=OPEN_DURATION_SECONDS + 60)
        p = HostPolicy(
            domain="x.com",
            circuit_state="open",
            circuit_opened_at=opened_long_ago,
        )
        assert p.effective_circuit_state() == "half_open"
        assert not p.is_blocked()

    def test_circuit_still_open_within_duration(self):
        p = HostPolicy(
            domain="x.com",
            circuit_state="open",
            circuit_opened_at=datetime.now(timezone.utc),
        )
        assert p.effective_circuit_state() == "open"
        assert p.is_blocked()

    def test_close_circuit_resets_failures(self):
        p = HostPolicy(
            domain="x.com",
            circuit_state="open",
            consecutive_failures=7,
        ).close_circuit()
        assert p.circuit_state == "closed"
        assert p.consecutive_failures == 0
        assert p.blocked_until is None


class TestEWMAUpdate:
    def test_first_sample_sets_ewma(self):
        p = HostPolicy(domain="x.com")
        updated = p.update_ewma(200)
        assert updated.latency_ewma_ms == 200

    def test_subsequent_sample_blends(self):
        p = HostPolicy(domain="x.com", latency_ewma_ms=100)
        updated = p.update_ewma(200)
        expected = int(EWMA_ALPHA * 200 + (1 - EWMA_ALPHA) * 100)
        assert updated.latency_ewma_ms == expected

    def test_does_not_mutate_original(self):
        p = HostPolicy(domain="x.com", latency_ewma_ms=100)
        _ = p.update_ewma(500)
        assert p.latency_ewma_ms == 100


class TestRegisterFailure:
    def test_increments_consecutive_failures(self):
        p = HostPolicy(domain="x.com")
        p2 = p.register_failure()
        assert p2.consecutive_failures == 1

    def test_opens_circuit_after_threshold(self):
        p = HostPolicy(domain="x.com", consecutive_failures=BLOCK_AFTER_CONSECUTIVE_FAILURES - 1)
        p2 = p.register_failure()
        assert p2.circuit_state == "open"

    def test_respects_retry_after(self):
        p = HostPolicy(domain="x.com")
        p2 = p.register_failure(retry_after_seconds=120)
        assert p2.blocked_until is not None
        now = datetime.now(timezone.utc)
        delta = (p2.blocked_until - now).total_seconds()
        assert 100 <= delta <= 140

    def test_no_retry_after_does_not_set_blocked_until_below_threshold(self):
        p = HostPolicy(domain="x.com", consecutive_failures=2)
        p2 = p.register_failure()
        assert p2.blocked_until is None

    def test_updates_http_status(self):
        p = HostPolicy(domain="x.com")
        p2 = p.register_failure(http_status=429)
        assert p2.last_http_status == 429


class TestRegisterSuccess:
    def test_resets_failures(self):
        p = HostPolicy(domain="x.com", consecutive_failures=3, circuit_state="open")
        p2 = p.register_success(latency_ms=150)
        assert p2.consecutive_failures == 0
        assert p2.circuit_state == "closed"
        assert p2.blocked_until is None

    def test_updates_ewma(self):
        p = HostPolicy(domain="x.com")
        p2 = p.register_success(latency_ms=300)
        assert p2.latency_ewma_ms == 300


class TestSuggestedDelay:
    def test_uses_min_delay_at_minimum(self):
        p = HostPolicy(domain="x.com", min_delay_seconds=2.0)
        assert p.suggested_delay_seconds() >= 2.0

    def test_respects_robots_crawl_delay(self):
        p = HostPolicy(
            domain="x.com", min_delay_seconds=1.0, crawl_delay_seconds=5.0
        )
        assert p.suggested_delay_seconds() == 5.0

    def test_ewma_adds_to_delay(self):
        p = HostPolicy(
            domain="x.com",
            min_delay_seconds=1.0,
            max_concurrency=1,
            latency_ewma_ms=10_000,
        )
        assert p.suggested_delay_seconds() >= 10.0


class TestEffectiveCircuitStateEdgeCases:
    def test_open_with_none_circuit_opened_at_returns_closed(self):
        p = HostPolicy(domain="x.com", circuit_state="open", circuit_opened_at=None)
        assert p.effective_circuit_state() == "closed"

    def test_blocked_until_future_is_blocked(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        p = HostPolicy(domain="x.com", blocked_until=future)
        assert p.is_blocked()


class TestGetHostPolicy:
    @pytest.mark.asyncio
    async def test_returns_default_when_not_found(self):
        conn = FakeConnection(fetchrow_result=None)
        policy = await get_host_policy(FakePool(conn), "new.com.br")
        assert policy.domain == "new.com.br"
        assert policy.circuit_state == "closed"
        assert policy.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_maps_row(self):
        now = datetime.now(timezone.utc)
        conn = FakeConnection(
            fetchrow_result={
                "consecutive_failures": 2,
                "blocked_until": None,
                "last_fetch_at": now,
                "crawl_delay_seconds": 2.5,
                "min_delay_seconds": 1.0,
                "max_concurrency": 2,
                "latency_ewma_ms": 400,
                "last_http_status": 200,
                "last_retry_after_at": None,
                "circuit_state": "closed",
                "circuit_opened_at": None,
                "crawl_budget_per_day": 30,
                "crawl_budget_used": 5,
                "crawl_budget_date": date.today(),
            }
        )
        policy = await get_host_policy(FakePool(conn), "acme.com.br")
        assert policy.consecutive_failures == 2
        assert policy.crawl_delay_seconds == 2.5
        assert policy.latency_ewma_ms == 400

    @pytest.mark.asyncio
    async def test_handles_null_fields(self):
        conn = FakeConnection(
            fetchrow_result={
                "consecutive_failures": None,
                "blocked_until": None,
                "last_fetch_at": None,
                "crawl_delay_seconds": None,
                "min_delay_seconds": None,
                "max_concurrency": None,
                "latency_ewma_ms": None,
                "last_http_status": None,
                "last_retry_after_at": None,
                "circuit_state": None,
                "circuit_opened_at": None,
                "crawl_budget_per_day": None,
                "crawl_budget_used": None,
                "crawl_budget_date": None,
            }
        )
        policy = await get_host_policy(FakePool(conn), "acme.com.br")
        assert policy.consecutive_failures == 0
        assert policy.circuit_state == "closed"
        assert policy.max_concurrency == 1


class TestSaveHostPolicy:
    @pytest.mark.asyncio
    async def test_executes_upsert(self):
        conn = FakeConnection()
        policy = HostPolicy(domain="acme.com.br", consecutive_failures=1)
        await save_host_policy(FakePool(conn), policy)
        assert len(conn.execute_calls) == 1
        _, args = conn.execute_calls[0]
        assert args[0] == "acme.com.br"
        assert args[1] == 1


class TestIncrementHostBudget:
    @pytest.mark.asyncio
    async def test_executes_increment(self):
        conn = FakeConnection()
        await increment_host_budget(FakePool(conn), "acme.com.br")
        assert len(conn.execute_calls) == 1
        _, args = conn.execute_calls[0]
        assert args[0] == "acme.com.br"
