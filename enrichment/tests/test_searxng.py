import httpx
import pytest

from discovery.errors import SearchRateLimitError, SearchTimeoutError, SearchUnavailableError
from discovery.search_queries import SearchQuery
from discovery.searxng import search_searxng


def _make_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=httpx.Timeout(5.0))


def _searxng_response(urls: list[str]) -> httpx.Response:
    return httpx.Response(200, json={
        "results": [{"url": u, "title": "Result", "content": ""} for u in urls]
    })


_QUERY = SearchQuery(text='"12.345.678/0001-90"', confidence_bonus=30, reason="cnpj_exact")


class TestSearchSearxng:
    @pytest.mark.asyncio
    async def test_returns_candidates_from_results(self):
        def handler(request):
            return _searxng_response(["https://empresa.com.br/sobre", "https://outra.com.br/"])

        async with _make_client(handler) as client:
            candidates = await search_searxng(_QUERY, client=client, base_url="http://searxng")

        assert len(candidates) >= 1
        assert candidates[0].domain == "empresa.com.br"
        assert candidates[0].source == "searxng"

    @pytest.mark.asyncio
    async def test_confidence_includes_query_bonus(self):
        def handler(request):
            return _searxng_response(["https://acme.com.br/"])

        async with _make_client(handler) as client:
            candidates = await search_searxng(_QUERY, client=client, base_url="http://searxng")

        assert candidates[0].confidence == min(55 + 30, 100)

    @pytest.mark.asyncio
    async def test_raises_unavailable_on_http_error(self):
        def handler(request):
            raise httpx.ConnectError("down", request=request)

        async with _make_client(handler) as client:
            with pytest.raises(SearchUnavailableError) as exc_info:
                await search_searxng(_QUERY, client=client, base_url="http://searxng")
        assert exc_info.value.source == "searxng"

    @pytest.mark.asyncio
    async def test_raises_unavailable_on_503(self):
        def handler(request):
            return httpx.Response(503)

        async with _make_client(handler) as client:
            with pytest.raises(SearchUnavailableError) as exc_info:
                await search_searxng(_QUERY, client=client, base_url="http://searxng")
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_raises_rate_limit_on_429(self):
        def handler(request):
            return httpx.Response(429)

        async with _make_client(handler) as client:
            with pytest.raises(SearchRateLimitError) as exc_info:
                await search_searxng(_QUERY, client=client, base_url="http://searxng")
        assert exc_info.value.source == "searxng"
        assert exc_info.value.retry_after == 30

    @pytest.mark.asyncio
    async def test_raises_timeout_on_timeout_error(self):
        def handler(request):
            raise httpx.TimeoutException("timeout", request=request)

        async with _make_client(handler) as client:
            with pytest.raises(SearchTimeoutError) as exc_info:
                await search_searxng(_QUERY, client=client, base_url="http://searxng")
        assert exc_info.value.source == "searxng"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_results(self):
        def handler(request):
            return httpx.Response(200, json={"results": []})

        async with _make_client(handler) as client:
            candidates = await search_searxng(_QUERY, client=client, base_url="http://searxng")

        assert candidates == []

    @pytest.mark.asyncio
    async def test_raises_unavailable_on_json_decode_error(self):
        def handler(request):
            return httpx.Response(200, content=b"not json", headers={"content-type": "text/html"})

        async with _make_client(handler) as client:
            with pytest.raises(SearchUnavailableError):
                await search_searxng(_QUERY, client=client, base_url="http://searxng")

    @pytest.mark.asyncio
    async def test_deduplicates_same_domain(self):
        def handler(request):
            return _searxng_response([
                "https://empresa.com.br/",
                "https://empresa.com.br/contato",
                "https://outro.com.br/",
            ])

        async with _make_client(handler) as client:
            candidates = await search_searxng(_QUERY, client=client, base_url="http://searxng")

        domains = [c.domain for c in candidates]
        assert domains.count("empresa.com.br") == 1

    @pytest.mark.asyncio
    async def test_filters_directory_domains(self):
        def handler(request):
            return _searxng_response([
                "https://facebook.com/empresa",
                "https://empresa.com.br/",
            ])

        async with _make_client(handler) as client:
            candidates = await search_searxng(_QUERY, client=client, base_url="http://searxng")

        domains = [c.domain for c in candidates]
        assert "facebook.com" not in domains
        assert "empresa.com.br" in domains

    @pytest.mark.asyncio
    async def test_respects_max_results(self):
        def handler(request):
            return _searxng_response([f"https://site{i}.com.br/" for i in range(10)])

        async with _make_client(handler) as client:
            candidates = await search_searxng(_QUERY, client=client, base_url="http://searxng")

        assert len(candidates) <= 3

    @pytest.mark.asyncio
    async def test_sends_query_text_as_q_param(self):
        params_seen = {}

        def handler(request):
            params_seen.update(dict(request.url.params))
            return _searxng_response(["https://acme.com.br/"])

        async with _make_client(handler) as client:
            await search_searxng(_QUERY, client=client, base_url="http://searxng")

        assert params_seen.get("q") == '"12.345.678/0001-90"'
        assert params_seen.get("format") == "json"
