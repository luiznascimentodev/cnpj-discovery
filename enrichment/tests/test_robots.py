import httpx
import pytest

from crawler.robots import (
    RobotsRules,
    _status_text,
    fetch_robots,
    persist_host_robots,
)


def _client(handler):
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=httpx.Timeout(5.0),
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
    def __init__(self):
        self.execute_calls = []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


class TestRobotsRules:
    def test_empty_raw_allows_all(self):
        rules = RobotsRules("acme.com.br", "", None, 200)

        assert rules.can_fetch("https://acme.com.br/private/", "MyBot") is True

    def test_disallow_blocks_matching_path(self):
        raw = "User-agent: *\nDisallow: /private/\nCrawl-delay: 5\n"
        rules = RobotsRules("acme.com.br", raw, 5.0, 200)

        assert rules.can_fetch("https://acme.com.br/private/secret", "MyBot") is False
        assert rules.can_fetch("https://acme.com.br/contato", "MyBot") is True


class TestFetchRobots:
    @pytest.mark.asyncio
    async def test_returns_rules_on_success(self):
        body = "User-agent: *\nDisallow: /admin/\nCrawl-delay: 3\n"

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/robots.txt"
            return httpx.Response(200, text=body)

        async with _client(handler) as client:
            rules = await fetch_robots("acme.com.br", client=client, user_agent="MyBot")

        assert rules.fetched_status == 200
        assert rules.crawl_delay == 3.0
        assert rules.can_fetch("https://acme.com.br/admin/", "MyBot") is False

    @pytest.mark.asyncio
    async def test_handles_404_as_open(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="not found")

        async with _client(handler) as client:
            rules = await fetch_robots("acme.com.br", client=client, user_agent="MyBot")

        assert rules.fetched_status == 404
        assert rules.raw == ""
        assert rules.can_fetch("https://acme.com.br/", "MyBot") is True

    @pytest.mark.asyncio
    async def test_handles_network_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        async with _client(handler) as client:
            rules = await fetch_robots("acme.com.br", client=client, user_agent="MyBot")

        assert rules.fetched_status == 0
        assert rules.raw == ""

    @pytest.mark.asyncio
    async def test_handles_robots_without_crawl_delay(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")

        async with _client(handler) as client:
            rules = await fetch_robots("acme.com.br", client=client, user_agent="MyBot")

        assert rules.crawl_delay is None


class TestStatusText:
    def test_ok_for_200(self):
        assert _status_text(200) == "ok"

    def test_missing_for_404(self):
        assert _status_text(404) == "missing"

    def test_unreachable_for_zero(self):
        assert _status_text(0) == "unreachable"

    def test_http_for_other_codes(self):
        assert _status_text(503) == "http_503"


class TestPersistHostRobots:
    @pytest.mark.asyncio
    async def test_upserts_status_and_delay(self):
        conn = FakeConnection()
        rules = RobotsRules("acme.com.br", "User-agent: *\n", 4.5, 200)

        await persist_host_robots(FakePool(conn), rules)

        query, args = conn.execute_calls[0]
        assert "INSERT INTO paid_enrichment.crawl_hosts" in query
        assert args == ("acme.com.br", "ok", 4.5)
