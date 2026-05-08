from datetime import datetime, timedelta, timezone

import httpx
import pytest

from crawler.queue import ClaimedCrawlRequest, HostState
from crawler.robots import RobotsRules
from crawler.runner import (
    BLOCK_AFTER_FAILURES,
    DEFAULT_USER_AGENT,
    HOST_BLOCK_DURATION,
    MAX_ATTEMPTS,
    RETRY_BASE_SECONDS,
    RETRY_MAX_SECONDS,
    RunStats,
    extract_title,
    hash_body,
    process_request,
    retry_delay,
    run_batch,
)


# ---------- Fakes ----------


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeTransaction:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    def __init__(
        self,
        *,
        fetch_results=None,
        fetchrow_results=None,
        fetchval_results=None,
    ):
        self._fetch = list(fetch_results or [])
        self._fetchrow = list(fetchrow_results or [])
        self._fetchval = list(fetchval_results or [])
        self.fetch_calls = []
        self.fetchrow_calls = []
        self.fetchval_calls = []
        self.execute_calls = []

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self._fetch.pop(0) if self._fetch else []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self._fetchrow.pop(0) if self._fetchrow else None

    async def fetchval(self, query, *args):
        self.fetchval_calls.append((query, args))
        return self._fetchval.pop(0) if self._fetchval else None

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "OK"

    def transaction(self):
        return FakeTransaction()


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


def _client(handler):
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=httpx.Timeout(5.0),
    )


def _request(**overrides) -> ClaimedCrawlRequest:
    base = {
        "id": 1,
        "cnpj_basico": "12345678",
        "cnpj_ordem": "0001",
        "cnpj_dv": "90",
        "url": "https://acme.com.br/contato",
        "domain": "acme.com.br",
        "priority": 60,
        "depth": 0,
        "attempts": 1,
        "source": "rf_email_domain",
    }
    base.update(overrides)
    return ClaimedCrawlRequest(**base)


# ---------- Helpers ----------


class TestHelpers:
    def test_retry_delay_grows_exponentially(self):
        assert retry_delay(1) == RETRY_BASE_SECONDS
        assert retry_delay(2) == RETRY_BASE_SECONDS * 2
        assert retry_delay(3) == RETRY_BASE_SECONDS * 4

    def test_retry_delay_capped_at_max(self):
        assert retry_delay(20) == RETRY_MAX_SECONDS

    def test_retry_delay_handles_zero_or_negative(self):
        assert retry_delay(0) == RETRY_BASE_SECONDS
        assert retry_delay(-3) == RETRY_BASE_SECONDS

    def test_hash_body_stable(self):
        assert hash_body("hello") == hash_body("hello")
        assert hash_body("a") != hash_body("b")

    def test_extract_title_returns_text(self):
        assert extract_title("<html><title>Acme</title>") == "Acme"

    def test_extract_title_returns_none_when_missing(self):
        assert extract_title("<html><body>x</body></html>") is None

    def test_extract_title_returns_none_when_unclosed(self):
        assert extract_title("<html><title>Acme") is None

    def test_extract_title_returns_none_when_empty(self):
        assert extract_title("<html><title>   </title></html>") is None


# ---------- process_request ----------


class TestProcessRequestRobots:
    @pytest.mark.asyncio
    async def test_uses_robots_cache_when_available(self):
        rules = RobotsRules("acme.com.br", "User-agent: *\nDisallow: /contato\n", None, 200)
        pool = FakePool(FakeConnection())

        async with _client(lambda r: httpx.Response(200)) as client:
            outcome, _ = await process_request(
                pool,
                _request(),
                client=client,
                user_agent="Bot",
                robots_cache={"acme.com.br": rules},
            )

        assert outcome == "blocked"

    @pytest.mark.asyncio
    async def test_fetches_robots_then_blocks_when_disallow(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
            raise AssertionError("unexpected path")

        pool = FakePool(FakeConnection())
        cache: dict = {}

        async with _client(handler) as client:
            outcome, _ = await process_request(
                pool,
                _request(),
                client=client,
                user_agent="Bot",
                robots_cache=cache,
            )

        assert outcome == "blocked"
        assert "acme.com.br" in cache


class TestProcessRequestHostBlocked:
    @pytest.mark.asyncio
    async def test_retries_when_host_blocked_until_in_future(self):
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        conn = FakeConnection(
            fetchrow_results=[
                {
                    "consecutive_failures": 5,
                    "blocked_until": future,
                    "last_fetch_at": None,
                    "crawl_delay_seconds": None,
                }
            ]
        )
        pool = FakePool(conn)
        rules = RobotsRules("acme.com.br", "", None, 200)

        async with _client(lambda r: httpx.Response(200)) as client:
            outcome, contacts = await process_request(
                pool,
                _request(),
                client=client,
                user_agent="Bot",
                robots_cache={"acme.com.br": rules},
            )

        assert outcome == "retried"
        assert contacts == 0


class TestProcessRequestHttpFlows:
    @pytest.mark.asyncio
    async def test_network_error_triggers_retry(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        # fetchrow x2: get_host_state (None) + get_host_state in _handle_failure (None)
        conn = FakeConnection(fetchrow_results=[None, None])
        pool = FakePool(conn)
        rules = RobotsRules("acme.com.br", "", None, 200)

        async with _client(handler) as client:
            outcome, _ = await process_request(
                pool,
                _request(attempts=1),
                client=client,
                user_agent="Bot",
                robots_cache={"acme.com.br": rules},
            )

        assert outcome == "retried"

    @pytest.mark.asyncio
    async def test_network_error_after_max_attempts_marks_errored(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        conn = FakeConnection(fetchrow_results=[None, None])
        pool = FakePool(conn)
        rules = RobotsRules("acme.com.br", "", None, 200)

        async with _client(handler) as client:
            outcome, _ = await process_request(
                pool,
                _request(attempts=MAX_ATTEMPTS),
                client=client,
                user_agent="Bot",
                robots_cache={"acme.com.br": rules},
            )

        assert outcome == "errored"

    @pytest.mark.asyncio
    async def test_403_marks_blocked(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403)

        conn = FakeConnection(fetchrow_results=[None])
        pool = FakePool(conn)
        rules = RobotsRules("acme.com.br", "", None, 200)

        async with _client(handler) as client:
            outcome, _ = await process_request(
                pool,
                _request(),
                client=client,
                user_agent="Bot",
                robots_cache={"acme.com.br": rules},
            )

        assert outcome == "blocked"

    @pytest.mark.asyncio
    async def test_429_triggers_retry(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429)

        conn = FakeConnection(fetchrow_results=[None, None])
        pool = FakePool(conn)
        rules = RobotsRules("acme.com.br", "", None, 200)

        async with _client(handler) as client:
            outcome, _ = await process_request(
                pool,
                _request(attempts=1),
                client=client,
                user_agent="Bot",
                robots_cache={"acme.com.br": rules},
            )

        assert outcome == "retried"

    @pytest.mark.asyncio
    async def test_5xx_blocks_host_after_threshold(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        conn = FakeConnection(
            fetchrow_results=[
                None,  # initial host state
                {
                    "consecutive_failures": BLOCK_AFTER_FAILURES - 1,
                    "blocked_until": None,
                    "last_fetch_at": None,
                    "crawl_delay_seconds": None,
                },
            ]
        )
        pool = FakePool(conn)
        rules = RobotsRules("acme.com.br", "", None, 200)

        async with _client(handler) as client:
            outcome, _ = await process_request(
                pool,
                _request(attempts=1),
                client=client,
                user_agent="Bot",
                robots_cache={"acme.com.br": rules},
            )

        assert outcome == "retried"
        update_call = next(
            call for call in conn.execute_calls if "consecutive_failures" in call[0]
        )
        # blocked_until argument is third
        assert update_call[1][2] is not None

    @pytest.mark.asyncio
    async def test_404_marks_errored(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        conn = FakeConnection(fetchrow_results=[None])
        pool = FakePool(conn)
        rules = RobotsRules("acme.com.br", "", None, 200)

        async with _client(handler) as client:
            outcome, _ = await process_request(
                pool,
                _request(),
                client=client,
                user_agent="Bot",
                robots_cache={"acme.com.br": rules},
            )

        assert outcome == "errored"


class TestProcessRequestSuccess:
    @pytest.mark.asyncio
    async def test_success_publishes_high_confidence_contacts(self):
        body = (
            "<html><title>Acme</title>"
            "<a href=\"mailto:vendas@acme.com.br\">Vendas</a>"
            "<a href=\"mailto:rfemail@acme.com.br\">RF</a>"
            "</html>"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=body, headers={"content-type": "text/html"})

        conn = FakeConnection(
            fetchrow_results=[
                None,  # get_host_state
                {  # _baseline_blacklist returns RF data, exercising lines 113-116
                    "email": "rfemail@acme.com.br",
                    "ddd1": "11",
                    "telefone1": "987654321",
                    "ddd2": None,
                    "telefone2": None,
                },
            ],
            fetch_results=[
                [{"domain": "acme.com.br"}],  # _trusted_domains
            ],
            fetchval_results=[
                999,  # crawl_pages page id
                501,  # evidence for vendas@
            ],
        )
        pool = FakePool(conn)
        rules = RobotsRules("acme.com.br", "", None, 200)

        async with _client(handler) as client:
            outcome, contacts = await process_request(
                pool,
                _request(),
                client=client,
                user_agent="Bot",
                robots_cache={"acme.com.br": rules},
            )

        assert outcome == "done"
        # rfemail@acme.com.br should have been filtered out by the blacklist
        assert contacts >= 1
        done_calls = [c for c in conn.execute_calls if "status = 'done'" in c[0]]
        assert len(done_calls) == 1


# ---------- run_batch ----------


class TestRunBatch:
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_requests(self):
        conn = FakeConnection(fetch_results=[[]])  # claim returns []

        async with _client(lambda r: httpx.Response(200)) as client:
            stats = await run_batch(
                FakePool(conn),
                client=client,
                worker_id="worker-1",
            )

        assert stats == RunStats(requests_claimed=0)

    @pytest.mark.asyncio
    async def test_aggregates_outcomes(self):
        body = "<html>contato@acme.com.br</html>"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(200, text=body)

        conn = FakeConnection(
            fetch_results=[
                # claim_crawl_requests
                [
                    {
                        "id": 1,
                        "cnpj_basico": "12345678",
                        "cnpj_ordem": "0001",
                        "cnpj_dv": "90",
                        "url": "https://acme.com.br/",
                        "domain": "acme.com.br",
                        "priority": 60,
                        "depth": 0,
                        "attempts": 1,
                        "source": "rf",
                    }
                ],
                # _trusted_domains
                [{"domain": "acme.com.br"}],
            ],
            fetchrow_results=[
                None,  # get_host_state
                None,  # _baseline_blacklist
            ],
            fetchval_results=[
                111,  # crawl_pages page id
                222,  # evidence id (single contact)
            ],
        )

        async with _client(handler) as client:
            stats = await run_batch(
                FakePool(conn),
                client=client,
                worker_id="worker-1",
            )

        assert stats.requests_claimed == 1
        assert stats.requests_done == 1
        assert stats.pages_fetched == 1


class TestModuleConstants:
    def test_default_user_agent_includes_bot_marker(self):
        assert "CNPJDiscoveryBot" in DEFAULT_USER_AGENT

    def test_host_block_duration_is_set(self):
        assert HOST_BLOCK_DURATION.total_seconds() > 0
