from datetime import datetime, timezone

import pytest

from crawler.domain_queue import (
    CANONICAL_PATHS,
    DEFAULT_CLAIM_BATCH,
    DEFAULT_LEASE_SECONDS,
    DEFAULT_RETRY_MAX_SECONDS,
    TERMINAL_DOMAIN_JOB_STATUSES,
    ClaimedDomainJob,
    claim_domain_crawl_jobs,
    complete_domain_crawl_job,
    enqueue_domain_jobs_for_domain,
    enqueue_jobs_from_verified_domains,
    enqueue_playwright_jobs_for_zero_contact_domains,
    jittered_backoff,
    release_stale_domain_jobs,
    retry_domain_crawl_job,
    terminal_domain_crawl_job,
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
    def __init__(self, *, fetch_results=None, fetchrow_results=None):
        self._fetch_results = list(fetch_results or [])
        self._fetchrow_results = list(fetchrow_results or [])
        self.fetch_calls = []
        self.execute_calls = []
        self.fetchrow_calls = []

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self._fetch_results.pop(0) if self._fetch_results else []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if self._fetchrow_results:
            return self._fetchrow_results.pop(0)
        return None

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


class TestJitteredBackoff:
    def test_first_attempt_is_close_to_base(self):
        delays = [jittered_backoff(1) for _ in range(50)]
        assert all(48 <= d <= 72 for d in delays)

    def test_grows_with_attempts(self):
        assert jittered_backoff(3, base=60) > jittered_backoff(1, base=60)

    def test_caps_at_max(self):
        for _ in range(20):
            assert jittered_backoff(20) <= DEFAULT_RETRY_MAX_SECONDS


class TestClaimDomainCrawlJobs:
    @pytest.mark.asyncio
    async def test_rejects_empty_worker_id(self):
        with pytest.raises(ValueError, match="worker_id"):
            await claim_domain_crawl_jobs(FakePool(FakeConnection()), worker_id="")

    @pytest.mark.asyncio
    async def test_rejects_zero_batch(self):
        with pytest.raises(ValueError, match="batch_size"):
            await claim_domain_crawl_jobs(
                FakePool(FakeConnection()), worker_id="w", batch_size=0
            )

    @pytest.mark.asyncio
    async def test_maps_rows_to_dataclass(self):
        conn = FakeConnection(
            fetch_results=[
                [
                    {
                        "id": 42,
                        "domain": "acme.com.br",
                        "url": "https://acme.com.br/",
                        "crawl_profile": "static_http",
                        "source": "verified_domain",
                        "priority": 80,
                        "depth": 0,
                        "attempts": 1,
                    }
                ]
            ]
        )

        jobs = await claim_domain_crawl_jobs(
            FakePool(conn), worker_id="w1", batch_size=5, lease_seconds=120
        )

        assert jobs == [
            ClaimedDomainJob(
                id=42,
                domain="acme.com.br",
                url="https://acme.com.br/",
                crawl_profile="static_http",
                source="verified_domain",
                priority=80,
                depth=0,
                attempts=1,
            )
        ]
        _, args = conn.fetch_calls[0]
        assert args == (5, 120, "w1", None)

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self):
        conn = FakeConnection(fetch_results=[[]])
        jobs = await claim_domain_crawl_jobs(FakePool(conn), worker_id="w")
        assert jobs == []

    @pytest.mark.asyncio
    async def test_uses_defaults(self):
        conn = FakeConnection(fetch_results=[[]])
        await claim_domain_crawl_jobs(FakePool(conn), worker_id="w")
        _, args = conn.fetch_calls[0]
        assert args == (DEFAULT_CLAIM_BATCH, DEFAULT_LEASE_SECONDS, "w", None)


class TestCompleteDomainCrawlJob:
    @pytest.mark.asyncio
    async def test_writes_correct_args(self):
        conn = FakeConnection()
        await complete_domain_crawl_job(
            FakePool(conn), 7, content_hash="abc123", http_status=200
        )
        assert conn.execute_calls[0][1] == (7, "abc123", 200)


class TestRetryDomainCrawlJob:
    @pytest.mark.asyncio
    async def test_clamps_negative_delay(self):
        conn = FakeConnection()
        await retry_domain_crawl_job(
            FakePool(conn), 5, retry_in_seconds=-10, last_error="err"
        )
        _, args = conn.execute_calls[0]
        assert args[1] == 0

    @pytest.mark.asyncio
    async def test_passes_http_status(self):
        conn = FakeConnection()
        await retry_domain_crawl_job(
            FakePool(conn), 5, retry_in_seconds=60, last_error="429", http_status=429
        )
        _, args = conn.execute_calls[0]
        assert args == (5, 60, "429", 429)


class TestTerminalDomainCrawlJob:
    @pytest.mark.asyncio
    async def test_rejects_invalid_status(self):
        with pytest.raises(ValueError, match="Invalid terminal status"):
            await terminal_domain_crawl_job(
                FakePool(FakeConnection()), 1, status="done"
            )

    @pytest.mark.asyncio
    async def test_accepts_blocked(self):
        conn = FakeConnection()
        await terminal_domain_crawl_job(
            FakePool(conn), 3, status="blocked", last_error="robots", http_status=None
        )
        _, args = conn.execute_calls[0]
        assert args == (3, "blocked", "robots", None)

    def test_terminal_set(self):
        assert TERMINAL_DOMAIN_JOB_STATUSES == {"error", "blocked", "skipped"}


class TestReleaseStaleJobs:
    @pytest.mark.asyncio
    async def test_returns_count(self):
        conn = FakeConnection(fetch_results=[[{"id": 1}, {"id": 2}, {"id": 3}]])
        released = await release_stale_domain_jobs(FakePool(conn), lease_seconds=300)
        assert released == 3
        assert conn.fetch_calls[0][1] == (300,)

    @pytest.mark.asyncio
    async def test_uses_default_lease(self):
        conn = FakeConnection(fetch_results=[[]])
        await release_stale_domain_jobs(FakePool(conn))
        assert conn.fetch_calls[0][1] == (DEFAULT_LEASE_SECONDS,)


class TestEnqueueDomainJobsForDomain:
    @pytest.mark.asyncio
    async def test_enqueues_canonical_paths(self):
        rows = [{"id": i + 1, "inserted": True} for i in range(len(CANONICAL_PATHS))]
        conn = FakeConnection(fetchrow_results=rows)
        count = await enqueue_domain_jobs_for_domain(
            FakePool(conn),
            domain="acme.com.br",
            homepage_url="https://acme.com.br",
            source="verified_domain",
            priority=70,
        )
        assert count == len(CANONICAL_PATHS)

    @pytest.mark.asyncio
    async def test_upsert_conflict_not_inserted_not_counted(self):
        rows = [{"id": i + 1, "inserted": False} for i in range(len(CANONICAL_PATHS))]
        conn = FakeConnection(fetchrow_results=rows)
        count = await enqueue_domain_jobs_for_domain(
            FakePool(conn),
            domain="acme.com.br",
            homepage_url=None,
            source="verified_domain",
            priority=50,
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_uses_https_domain_when_no_homepage(self):
        conn = FakeConnection(
            fetchrow_results=[{"id": 1, "inserted": True}] + [None] * 20
        )
        await enqueue_domain_jobs_for_domain(
            FakePool(conn),
            domain="example.com.br",
            homepage_url=None,
            source="test",
            priority=50,
            paths=["/"],
        )
        _, args = conn.fetchrow_calls[0]
        assert "https://example.com.br/" in args

    @pytest.mark.asyncio
    async def test_custom_paths(self):
        paths = ["/contato", "/sobre"]
        rows = [{"id": i + 1, "inserted": True} for i in range(len(paths))]
        conn = FakeConnection(fetchrow_results=rows)
        count = await enqueue_domain_jobs_for_domain(
            FakePool(conn),
            domain="acme.com.br",
            homepage_url="https://acme.com.br",
            source="x",
            priority=50,
            paths=paths,
        )
        assert count == len(paths)


class TestEnqueueJobsFromVerifiedDomains:
    @pytest.mark.asyncio
    async def test_enqueues_for_each_domain(self):
        verified_rows = [
            {"id": 10, "domain": "alpha.com.br", "homepage_url": "https://alpha.com.br"},
            {"id": 11, "domain": "beta.com.br", "homepage_url": None},
        ]
        # fetch_results: first call to get verified domains, then per-domain enqueue calls
        # enqueue_domain_jobs_for_domain uses fetchrow internally (one per path)
        # We simulate by providing inserted=True for each path per domain
        paths_count = len(CANONICAL_PATHS)
        inserted_rows = [{"id": i + 1, "inserted": True} for i in range(paths_count * 2)]
        conn = FakeConnection(
            fetch_results=[verified_rows],
            fetchrow_results=inserted_rows,
        )
        domains_seen, jobs_inserted = await enqueue_jobs_from_verified_domains(
            FakePool(conn), cursor_id=0, batch_size=100
        )
        assert domains_seen == 2
        assert jobs_inserted == paths_count * 2

    @pytest.mark.asyncio
    async def test_empty_verified_domains(self):
        conn = FakeConnection(fetch_results=[[]])
        domains_seen, jobs_inserted = await enqueue_jobs_from_verified_domains(
            FakePool(conn)
        )
        assert domains_seen == 0
        assert jobs_inserted == 0


class TestEnqueuePlaywrightJobsForZeroContactDomains:
    @pytest.mark.asyncio
    async def test_enqueues_playwright_paths(self):
        from crawler.domain_queue import PLAYWRIGHT_PROBE_PATHS

        zero_contact_rows = [
            {"domain": "js-only.com.br", "homepage_url": "https://js-only.com.br"},
        ]
        inserted_rows = [{"id": i + 1, "inserted": True} for i in range(len(PLAYWRIGHT_PROBE_PATHS))]
        conn = FakeConnection(
            fetch_results=[zero_contact_rows],
            fetchrow_results=inserted_rows,
        )
        domains_seen, jobs_inserted = await enqueue_playwright_jobs_for_zero_contact_domains(
            FakePool(conn), batch_size=50
        )
        assert domains_seen == 1
        assert jobs_inserted == len(PLAYWRIGHT_PROBE_PATHS)

    @pytest.mark.asyncio
    async def test_empty_returns_zeros(self):
        conn = FakeConnection(fetch_results=[[]])
        domains_seen, jobs_inserted = await enqueue_playwright_jobs_for_zero_contact_domains(
            FakePool(conn)
        )
        assert domains_seen == 0
        assert jobs_inserted == 0
