import httpx
import pytest

from discovery.website_probe import (
    DEFAULT_USER_AGENT,
    ProbeResult,
    is_parked,
    make_default_client,
    probe_domain,
)


def _client(handler):
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": DEFAULT_USER_AGENT},
        timeout=httpx.Timeout(5.0),
    )


class TestIsParked:
    def test_returns_false_for_empty(self):
        assert is_parked("") is False

    def test_detects_parked_keywords(self):
        assert is_parked("This Domain is For Sale right now") is True

    def test_returns_false_for_normal_html(self):
        assert is_parked("<html><body>Bem vindo à Acme</body></html>") is False


class TestProbeDomain:
    @pytest.mark.asyncio
    async def test_returns_https_response_when_available(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.scheme == "https"
            return httpx.Response(
                200,
                content=b"<html><title>Acme</title></html>",
                headers={"content-type": "text/html"},
            )

        async with _client(handler) as client:
            result = await probe_domain("acme.com.br", client=client)

        assert isinstance(result, ProbeResult)
        assert result.ok is True
        assert result.http_status == 200
        assert result.parked is False
        assert result.body.startswith("<html>")
        assert result.content_type == "text/html"

    @pytest.mark.asyncio
    async def test_falls_back_to_http_when_https_fails(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.scheme == "https":
                raise httpx.ConnectError("no ssl", request=request)
            return httpx.Response(200, content=b"<html>OK</html>")

        async with _client(handler) as client:
            result = await probe_domain("acme.com.br", client=client)

        assert result.http_status == 200
        assert result.final_url.startswith("http://")

    @pytest.mark.asyncio
    async def test_returns_error_when_all_attempts_fail(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        async with _client(handler) as client:
            result = await probe_domain("dead.com.br", client=client)

        assert result.ok is False
        assert result.http_status == 0
        assert "ConnectError" in (result.error or "")

    @pytest.mark.asyncio
    async def test_marks_parked_when_keywords_found(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"This domain is for sale!")

        async with _client(handler) as client:
            result = await probe_domain("parked.com.br", client=client)

        assert result.parked is True
        assert result.ok is True

    @pytest.mark.asyncio
    async def test_truncates_body_to_max_bytes(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"a" * 1000)

        async with _client(handler) as client:
            result = await probe_domain("acme.com.br", client=client, max_bytes=10)

        assert len(result.body) == 10


class TestMakeDefaultClient:
    @pytest.mark.asyncio
    async def test_factory_uses_provided_user_agent(self):
        async with make_default_client(user_agent="CustomBot/1.0") as client:
            assert client.headers["User-Agent"] == "CustomBot/1.0"

    @pytest.mark.asyncio
    async def test_factory_uses_default_user_agent_when_omitted(self):
        async with make_default_client() as client:
            assert client.headers["User-Agent"] == DEFAULT_USER_AGENT
