from datetime import datetime, timedelta, timezone

import pytest

from crawler.queue import (
    ClaimedCrawlRequest,
    DEFAULT_CLAIM_BATCH,
    DEFAULT_LEASE_SECONDS,
    HostState,
    TERMINAL_REQUEST_STATUSES,
    claim_crawl_requests,
    get_host_state,
    mark_request_done,
    mark_request_retry,
    mark_request_terminal,
    release_stale_requests,
    reset_host_failures,
    update_host_failures,
)


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


class FakeConnection:
    def __init__(self, *, fetch_results=None, fetchrow_result=None):
        self._fetch_results = list(fetch_results or [])
        self._fetchrow_result = fetchrow_result
        self.fetch_calls = []
        self.execute_calls = []

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self._fetch_results.pop(0) if self._fetch_results else []

    async def fetchrow(self, query, *args):
        return self._fetchrow_result

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


class TestClaimCrawlRequests:
    @pytest.mark.asyncio
    async def test_rejects_empty_worker(self):
        with pytest.raises(ValueError, match="worker_id"):
            await claim_crawl_requests(FakePool(FakeConnection()), worker_id="")

    @pytest.mark.asyncio
    async def test_rejects_zero_batch(self):
        with pytest.raises(ValueError, match="batch_size"):
            await claim_crawl_requests(
                FakePool(FakeConnection()), worker_id="w", batch_size=0
            )

    @pytest.mark.asyncio
    async def test_maps_rows_to_dataclasses(self):
        conn = FakeConnection(
            fetch_results=[
                [
                    {
                        "id": 99,
                        "cnpj_basico": "12345678",
                        "cnpj_ordem": "0001",
                        "cnpj_dv": "90",
                        "url": "https://acme.com.br/contato",
                        "domain": "acme.com.br",
                        "priority": 75,
                        "depth": 0,
                        "attempts": 1,
                        "source": "rf_email_domain",
                    }
                ]
            ]
        )

        result = await claim_crawl_requests(
            FakePool(conn),
            worker_id="worker-A",
            batch_size=10,
            lease_seconds=120,
        )

        assert result == [
            ClaimedCrawlRequest(
                id=99,
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                url="https://acme.com.br/contato",
                domain="acme.com.br",
                priority=75,
                depth=0,
                attempts=1,
                source="rf_email_domain",
            )
        ]
        assert conn.fetch_calls[0][1] == ("worker-A", 120, 10)

    @pytest.mark.asyncio
    async def test_uses_defaults_when_omitted(self):
        conn = FakeConnection(fetch_results=[[]])

        await claim_crawl_requests(FakePool(conn), worker_id="w")

        assert conn.fetch_calls[0][1] == ("w", DEFAULT_LEASE_SECONDS, DEFAULT_CLAIM_BATCH)


class TestMarkRequestStatuses:
    @pytest.mark.asyncio
    async def test_mark_done_writes_hash(self):
        conn = FakeConnection()

        await mark_request_done(FakePool(conn), 1, "deadbeef")

        assert conn.execute_calls[0][1] == (1, "deadbeef")

    @pytest.mark.asyncio
    async def test_mark_retry_clamps_negative_delay(self):
        conn = FakeConnection()

        await mark_request_retry(
            FakePool(conn),
            7,
            retry_in_seconds=-15,
            last_error="boom",
        )

        assert conn.execute_calls[0][1] == (7, 0, "boom")

    @pytest.mark.asyncio
    async def test_mark_terminal_rejects_invalid_status(self):
        with pytest.raises(ValueError, match="Invalid terminal status"):
            await mark_request_terminal(
                FakePool(FakeConnection()),
                42,
                status="done",
            )

    @pytest.mark.asyncio
    async def test_mark_terminal_accepts_blocked(self):
        conn = FakeConnection()

        await mark_request_terminal(FakePool(conn), 42, status="blocked", last_error="403")

        assert conn.execute_calls[0][1] == (42, "blocked", "403")

    def test_terminal_set_excludes_done(self):
        assert "done" not in TERMINAL_REQUEST_STATUSES
        assert TERMINAL_REQUEST_STATUSES == {"error", "blocked", "skipped"}


class TestReleaseStaleRequests:
    @pytest.mark.asyncio
    async def test_returns_released_count(self):
        conn = FakeConnection(fetch_results=[[{"id": 1}, {"id": 2}]])

        released = await release_stale_requests(FakePool(conn), lease_seconds=300)

        assert released == 2
        assert conn.fetch_calls[0][1] == (300,)


class TestHostState:
    @pytest.mark.asyncio
    async def test_get_host_state_returns_none_when_unknown(self):
        conn = FakeConnection(fetchrow_result=None)

        assert await get_host_state(FakePool(conn), "x.com") is None

    @pytest.mark.asyncio
    async def test_get_host_state_maps_row(self):
        when = datetime(2026, 5, 8, tzinfo=timezone.utc)
        conn = FakeConnection(
            fetchrow_result={
                "consecutive_failures": 4,
                "blocked_until": when,
                "last_fetch_at": when,
                "crawl_delay_seconds": 5,
            }
        )

        state = await get_host_state(FakePool(conn), "acme.com.br")

        assert state == HostState(
            consecutive_failures=4,
            blocked_until=when,
            last_fetch_at=when,
            crawl_delay_seconds=5.0,
        )

    @pytest.mark.asyncio
    async def test_get_host_state_handles_null_failures_and_delay(self):
        conn = FakeConnection(
            fetchrow_result={
                "consecutive_failures": None,
                "blocked_until": None,
                "last_fetch_at": None,
                "crawl_delay_seconds": None,
            }
        )

        state = await get_host_state(FakePool(conn), "acme.com.br")

        assert state == HostState(
            consecutive_failures=0,
            blocked_until=None,
            last_fetch_at=None,
            crawl_delay_seconds=None,
        )

    @pytest.mark.asyncio
    async def test_update_host_failures_writes_args(self):
        conn = FakeConnection()
        block_until = datetime(2026, 5, 8, tzinfo=timezone.utc) + timedelta(hours=1)

        await update_host_failures(
            FakePool(conn),
            "acme.com.br",
            consecutive_failures=3,
            blocked_until=block_until,
            last_fetch_at=block_until,
        )

        assert conn.execute_calls[0][1] == (
            "acme.com.br",
            3,
            block_until,
            block_until,
        )

    @pytest.mark.asyncio
    async def test_reset_host_failures(self):
        conn = FakeConnection()

        await reset_host_failures(FakePool(conn), "acme.com.br")

        assert conn.execute_calls[0][1] == ("acme.com.br",)
