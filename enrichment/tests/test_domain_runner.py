from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from crawler.domain_queue import ClaimedDomainJob
from crawler.domain_runner import (
    DEFAULT_USER_AGENT,
    DomainRunStats,
    MAX_ATTEMPTS,
    _clean_text,
    _extract_title,
    _hash_body,
    _parse_retry_after,
    process_domain_job,
    run_domain_batch,
)
from crawler.host_policy import HostPolicy
from crawler.robots import RobotsRules


# ---------- Helpers ----------


def make_job(**kwargs) -> ClaimedDomainJob:
    defaults = dict(
        id=1,
        domain="acme.com.br",
        url="https://acme.com.br/",
        crawl_profile="static_http",
        source="verified_domain",
        priority=50,
        depth=0,
        attempts=1,
    )
    defaults.update(kwargs)
    return ClaimedDomainJob(**defaults)


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_):
        return False


class FakeTransaction:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *_):
        return False


class FakeConnection:
    def __init__(self, *, fetchrow_results=None, fetchval_results=None, fetch_results=None):
        self._fetchrow = list(fetchrow_results or [])
        self._fetchval = list(fetchval_results or [])
        self._fetch = list(fetch_results or [])
        self.execute_calls = []

    async def fetchrow(self, query, *args):
        return self._fetchrow.pop(0) if self._fetchrow else None

    async def fetchval(self, query, *args):
        return self._fetchval.pop(0) if self._fetchval else None

    async def fetch(self, query, *args):
        return self._fetch.pop(0) if self._fetch else []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))

    def transaction(self):
        return FakeTransaction()


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


def make_response(status_code: int, text: str = "<html>hi</html>", headers=None) -> httpx.Response:
    h = {"content-type": "text/html"}
    if headers:
        h.update(headers)
    return httpx.Response(status_code, text=text, headers=h)


# ---------- Pure utility tests ----------


class TestExtractTitle:
    def test_extracts_title(self):
        assert _extract_title("<html><title>Olá</title></html>") == "Olá"

    def test_none_when_missing(self):
        assert _extract_title("<html>no title</html>") is None

    def test_case_insensitive(self):
        assert _extract_title("<TITLE>Hello</TITLE>") == "Hello"


class TestHashBody:
    def test_deterministic(self):
        assert _hash_body("abc") == _hash_body("abc")

    def test_different_inputs(self):
        assert _hash_body("a") != _hash_body("b")


class TestCleanText:
    def test_removes_null_bytes(self):
        assert _clean_text("a\x00b") == "ab"


class TestParseRetryAfter:
    def test_parses_integer(self):
        h = httpx.Headers({"retry-after": "120"})
        assert _parse_retry_after(h) == 120

    def test_returns_none_when_missing(self):
        h = httpx.Headers({})
        assert _parse_retry_after(h) is None

    def test_returns_none_for_non_integer(self):
        h = httpx.Headers({"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"})
        assert _parse_retry_after(h) is None

    def test_clamps_negative_to_zero(self):
        h = httpx.Headers({"retry-after": "-5"})
        assert _parse_retry_after(h) == 0


# ---------- process_domain_job tests ----------


@pytest.fixture
def open_rules():
    return RobotsRules(domain="acme.com.br", raw="", fetched_status=200, crawl_delay=None)


@pytest.fixture
def disallow_rules():
    return RobotsRules(
        domain="acme.com.br",
        raw="User-agent: *\nDisallow: /",
        fetched_status=200,
        crawl_delay=None,
    )


@pytest.fixture
def default_policy():
    return HostPolicy(domain="acme.com.br")


@pytest.fixture
def blocked_policy():
    from datetime import timedelta
    p = HostPolicy(domain="acme.com.br")
    return p.open_circuit()


async def _run_job(pool, job, *, client, policy=None, rules=None):
    robots_cache = {"acme.com.br": rules or RobotsRules(
        domain="acme.com.br", raw="", fetched_status=200, crawl_delay=None
    )}
    policy_cache = {}
    if policy is not None:
        policy_cache["acme.com.br"] = policy
    return await process_domain_job(
        pool, job,
        client=client,
        user_agent=DEFAULT_USER_AGENT,
        robots_cache=robots_cache,
        policy_cache=policy_cache,
    )


class TestProcessDomainJobBlocked:
    @pytest.mark.asyncio
    async def test_blocked_host_triggers_retry(self, blocked_policy):
        conn = FakeConnection(
            fetchrow_results=[
                # get_host_policy not called because policy already in cache
            ]
        )
        pool = FakePool(conn)
        client = MagicMock()

        with patch("crawler.domain_runner.retry_domain_crawl_job", new_callable=AsyncMock) as mock_retry, \
             patch("crawler.domain_runner.get_host_policy", new_callable=AsyncMock, return_value=blocked_policy):
            outcome, contacts = await _run_job(pool, make_job(), client=client, policy=blocked_policy)

        assert outcome == "retried"
        assert contacts == 0
        mock_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_robots_disallow_marks_blocked(self, default_policy, disallow_rules):
        conn = FakeConnection()
        pool = FakePool(conn)
        client = MagicMock()

        with patch("crawler.domain_runner.terminal_domain_crawl_job", new_callable=AsyncMock) as mock_term, \
             patch("crawler.domain_runner.get_host_policy", new_callable=AsyncMock, return_value=default_policy):
            outcome, contacts = await _run_job(
                pool, make_job(), client=client, rules=disallow_rules
            )

        assert outcome == "blocked"
        mock_term.assert_called_once()
        _, kwargs = mock_term.call_args
        assert kwargs["status"] == "blocked"


class TestProcessDomainJobHTTPErrors:
    @pytest.mark.asyncio
    async def test_403_marks_blocked(self, default_policy, open_rules):
        conn = FakeConnection()
        pool = FakePool(conn)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_response(403))

        with patch("crawler.domain_runner.terminal_domain_crawl_job", new_callable=AsyncMock) as mock_term, \
             patch("crawler.domain_runner.get_host_policy", new_callable=AsyncMock, return_value=default_policy), \
             patch("crawler.domain_runner.save_host_policy", new_callable=AsyncMock):
            outcome, contacts = await _run_job(
                pool, make_job(), client=mock_client, policy=default_policy, rules=open_rules
            )

        assert outcome == "blocked"
        _, kwargs = mock_term.call_args
        assert kwargs["status"] == "blocked"

    @pytest.mark.asyncio
    async def test_429_retries_with_retry_after(self, default_policy, open_rules):
        conn = FakeConnection()
        pool = FakePool(conn)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=make_response(429, headers={"retry-after": "90"})
        )

        with patch("crawler.domain_runner.retry_domain_crawl_job", new_callable=AsyncMock) as mock_retry, \
             patch("crawler.domain_runner.get_host_policy", new_callable=AsyncMock, return_value=default_policy), \
             patch("crawler.domain_runner.save_host_policy", new_callable=AsyncMock):
            outcome, contacts = await _run_job(
                pool, make_job(), client=mock_client, policy=default_policy, rules=open_rules
            )

        assert outcome == "retried"
        _, kwargs = mock_retry.call_args
        assert kwargs["retry_in_seconds"] == 90

    @pytest.mark.asyncio
    async def test_max_attempts_errored(self, default_policy, open_rules):
        conn = FakeConnection()
        pool = FakePool(conn)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_response(500))
        job = make_job(attempts=MAX_ATTEMPTS)

        with patch("crawler.domain_runner.terminal_domain_crawl_job", new_callable=AsyncMock) as mock_term, \
             patch("crawler.domain_runner.get_host_policy", new_callable=AsyncMock, return_value=default_policy), \
             patch("crawler.domain_runner.save_host_policy", new_callable=AsyncMock):
            outcome, contacts = await _run_job(
                pool, job, client=mock_client, policy=default_policy, rules=open_rules
            )

        assert outcome == "errored"
        _, kwargs = mock_term.call_args
        assert kwargs["status"] == "error"

    @pytest.mark.asyncio
    async def test_network_error_retries(self, default_policy, open_rules):
        conn = FakeConnection()
        pool = FakePool(conn)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with patch("crawler.domain_runner.retry_domain_crawl_job", new_callable=AsyncMock) as mock_retry, \
             patch("crawler.domain_runner.get_host_policy", new_callable=AsyncMock, return_value=default_policy), \
             patch("crawler.domain_runner.save_host_policy", new_callable=AsyncMock):
            outcome, contacts = await _run_job(
                pool, make_job(), client=mock_client, policy=default_policy, rules=open_rules
            )

        assert outcome == "retried"
        mock_retry.assert_called_once()


class TestProcessDomainJobSuccess:
    @pytest.mark.asyncio
    async def test_200_extracts_and_completes(self, default_policy, open_rules):
        html = "<html><title>Acme</title><a href='mailto:test@acme.com.br'>Contact</a></html>"
        conn = FakeConnection(
            fetchval_results=[99],  # page insert ID
            fetchrow_results=[{"id": 1}],  # contact insert
        )
        pool = FakePool(conn)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_response(200, text=html))

        with patch("crawler.domain_runner.complete_domain_crawl_job", new_callable=AsyncMock) as mock_complete, \
             patch("crawler.domain_runner.save_host_policy", new_callable=AsyncMock), \
             patch("crawler.domain_runner.increment_host_budget", new_callable=AsyncMock), \
             patch("crawler.domain_runner.get_host_policy", new_callable=AsyncMock, return_value=default_policy):
            outcome, contacts = await _run_job(
                pool, make_job(), client=mock_client, policy=default_policy, rules=open_rules
            )

        assert outcome == "done"
        mock_complete.assert_called_once()


class TestBlockedHostWithBlockedUntil:
    @pytest.mark.asyncio
    async def test_blocked_until_computes_real_delay(self, open_rules):
        future = datetime.now(timezone.utc) + timedelta(seconds=300)
        policy = HostPolicy(
            domain="acme.com.br",
            circuit_state="open",
            circuit_opened_at=datetime.now(timezone.utc),
            blocked_until=future,
        )
        conn = FakeConnection()
        pool = FakePool(conn)
        client = MagicMock()

        with patch("crawler.domain_runner.retry_domain_crawl_job", new_callable=AsyncMock) as mock_retry, \
             patch("crawler.domain_runner.get_host_policy", new_callable=AsyncMock, return_value=policy):
            outcome, contacts = await _run_job(
                pool, make_job(), client=client, policy=policy, rules=open_rules
            )

        assert outcome == "retried"
        _, kwargs = mock_retry.call_args
        assert kwargs["retry_in_seconds"] >= 1


class TestNetworkErrorMaxAttempts:
    @pytest.mark.asyncio
    async def test_network_error_at_max_attempts_marks_errored(self, default_policy, open_rules):
        conn = FakeConnection()
        pool = FakePool(conn)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        job = make_job(attempts=MAX_ATTEMPTS)

        with patch("crawler.domain_runner.terminal_domain_crawl_job", new_callable=AsyncMock) as mock_term, \
             patch("crawler.domain_runner.get_host_policy", new_callable=AsyncMock, return_value=default_policy), \
             patch("crawler.domain_runner.save_host_policy", new_callable=AsyncMock):
            outcome, contacts = await _run_job(
                pool, job, client=mock_client, policy=default_policy, rules=open_rules
            )

        assert outcome == "errored"
        _, kwargs = mock_term.call_args
        assert kwargs["status"] == "error"


class TestExtractTitleEdgeCases:
    def test_returns_none_when_close_tag_missing(self):
        assert _extract_title("<html><title>no close") is None


class TestBudgetExhausted:
    @pytest.mark.asyncio
    async def test_budget_exhausted_triggers_retry(self, open_rules):
        from datetime import date

        exhausted_policy = HostPolicy(
            domain="acme.com.br",
            crawl_budget_per_day=5,
            crawl_budget_used=5,
            crawl_budget_date=date.today(),
        )
        conn = FakeConnection()
        pool = FakePool(conn)
        client = MagicMock()

        with patch("crawler.domain_runner.retry_domain_crawl_job", new_callable=AsyncMock) as mock_retry, \
             patch("crawler.domain_runner.get_host_policy", new_callable=AsyncMock, return_value=exhausted_policy):
            outcome, contacts = await _run_job(
                pool, make_job(), client=client, policy=exhausted_policy, rules=open_rules
            )

        assert outcome == "budget_skipped"
        mock_retry.assert_called_once()


class TestUncachedRobots:
    @pytest.mark.asyncio
    async def test_fetches_robots_when_not_cached(self, default_policy):
        from crawler.robots import RobotsRules
        conn = FakeConnection()
        pool = FakePool(conn)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_response(200))
        open_rules = RobotsRules(domain="acme.com.br", raw="", fetched_status=200, crawl_delay=None)

        with patch("crawler.domain_runner.fetch_robots", new_callable=AsyncMock, return_value=open_rules), \
             patch("crawler.domain_runner.persist_host_robots", new_callable=AsyncMock), \
             patch("crawler.domain_runner.complete_domain_crawl_job", new_callable=AsyncMock), \
             patch("crawler.domain_runner.save_host_policy", new_callable=AsyncMock), \
             patch("crawler.domain_runner.increment_host_budget", new_callable=AsyncMock), \
             patch("crawler.domain_runner.get_host_policy", new_callable=AsyncMock, return_value=default_policy):
            outcome, contacts = await process_domain_job(
                pool, make_job(),
                client=mock_client,
                user_agent=DEFAULT_USER_AGENT,
                robots_cache={},
                policy_cache={},
            )

        assert outcome == "done"


class TestHTTP4xxNonBlocked:
    @pytest.mark.asyncio
    async def test_4xx_non_blocked_marks_error(self, default_policy, open_rules):
        conn = FakeConnection()
        pool = FakePool(conn)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_response(404))

        with patch("crawler.domain_runner.terminal_domain_crawl_job", new_callable=AsyncMock) as mock_term, \
             patch("crawler.domain_runner.get_host_policy", new_callable=AsyncMock, return_value=default_policy):
            outcome, contacts = await _run_job(
                pool, make_job(), client=mock_client, policy=default_policy, rules=open_rules
            )

        assert outcome == "errored"
        _, kwargs = mock_term.call_args
        assert kwargs["status"] == "error"


class TestBlockedHostNoBlockedUntil:
    @pytest.mark.asyncio
    async def test_open_circuit_no_blocked_until_uses_default_delay(self, open_rules):
        open_policy = HostPolicy(
            domain="acme.com.br",
            circuit_state="open",
            circuit_opened_at=datetime.now(timezone.utc),
            blocked_until=None,
        )
        conn = FakeConnection()
        pool = FakePool(conn)
        client = MagicMock()

        with patch("crawler.domain_runner.retry_domain_crawl_job", new_callable=AsyncMock) as mock_retry, \
             patch("crawler.domain_runner.get_host_policy", new_callable=AsyncMock, return_value=open_policy):
            outcome, contacts = await _run_job(
                pool, make_job(), client=client, policy=open_policy, rules=open_rules
            )

        assert outcome == "retried"
        _, kwargs = mock_retry.call_args
        assert kwargs["retry_in_seconds"] == 60


class TestRunDomainBatch:
    @pytest.mark.asyncio
    async def test_empty_queue_returns_zero_stats(self):
        with patch("crawler.domain_runner.claim_domain_crawl_jobs", new_callable=AsyncMock, return_value=[]):
            stats = await run_domain_batch(
                MagicMock(), client=MagicMock(), worker_id="w"
            )
        assert stats == DomainRunStats(jobs_claimed=0)

    @pytest.mark.asyncio
    async def test_aggregates_counters(self):
        jobs = [make_job(id=i + 1) for i in range(3)]

        async def fake_process(pool, job, **kwargs):
            return ("done", 2) if job.id == 1 else ("retried", 0)

        with patch("crawler.domain_runner.claim_domain_crawl_jobs", new_callable=AsyncMock, return_value=jobs), \
             patch("crawler.domain_runner.process_domain_job", side_effect=fake_process):
            stats = await run_domain_batch(
                MagicMock(), client=MagicMock(), worker_id="w"
            )

        assert stats.jobs_claimed == 3
        assert stats.jobs_done == 1
        assert stats.jobs_retried == 2
        assert stats.contacts_extracted == 2
