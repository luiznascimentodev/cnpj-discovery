import httpx
import pytest

from discovery.brave_search import _DIRECTORY_DOMAINS, _MAX_RESULTS, search_company_domain, search_with_queries
from discovery.errors import SearchRateLimitError, SearchTimeoutError, SearchUnavailableError
from discovery.search_queries import SearchQuery


def _make_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=httpx.Timeout(5.0))


def _brave_response(results: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"web": {"results": results}})


def _result(url: str, title: str = "Empresa") -> dict:
    return {"url": url, "title": title}


class TestSearchCompanyDomain:
    @pytest.mark.asyncio
    async def test_returns_candidates_for_valid_results(self):
        def handler(_request):
            return _brave_response([
                _result("https://www.acmebrasil.com.br"),
                _result("https://acmebrasil.com"),
            ])

        async with _make_client(handler) as client:
            candidates = await search_company_domain(
                "Acme Brasil", "São Paulo", client=client, api_key="key"
            )

        assert len(candidates) == 2
        assert candidates[0].domain == "acmebrasil.com.br"
        assert candidates[0].source == "brave_search"
        assert candidates[0].confidence == 55
        assert candidates[1].domain == "acmebrasil.com"

    @pytest.mark.asyncio
    async def test_filters_directory_domains(self):
        def handler(_request):
            return _brave_response([
                _result("https://www.jusbrasil.com.br/empresa/acme"),
                _result("https://acmebrasil.com.br"),
                _result("https://linkedin.com/company/acme"),
            ])

        async with _make_client(handler) as client:
            candidates = await search_company_domain(
                "Acme", None, client=client, api_key="key"
            )

        domains = [c.domain for c in candidates]
        assert "jusbrasil.com.br" not in domains
        assert "linkedin.com" not in domains
        assert "acmebrasil.com.br" in domains

    @pytest.mark.asyncio
    async def test_limits_to_max_results(self):
        def handler(_request):
            return _brave_response([
                _result(f"https://empresa{i}.com.br") for i in range(5)
            ])

        async with _make_client(handler) as client:
            candidates = await search_company_domain(
                "Empresa", None, client=client, api_key="key"
            )

        assert len(candidates) <= _MAX_RESULTS

    @pytest.mark.asyncio
    async def test_deduplicates_same_domain(self):
        def handler(_request):
            return _brave_response([
                _result("https://acme.com.br/sobre"),
                _result("https://www.acme.com.br/contato"),
            ])

        async with _make_client(handler) as client:
            candidates = await search_company_domain(
                "Acme", None, client=client, api_key="key"
            )

        assert len(candidates) == 1
        assert candidates[0].domain == "acme.com.br"

    @pytest.mark.asyncio
    async def test_raises_rate_limit_on_429(self):
        def handler(_request):
            return httpx.Response(429)

        async with _make_client(handler) as client:
            with pytest.raises(SearchRateLimitError) as exc_info:
                await search_company_domain("Acme", None, client=client, api_key="key")
        assert exc_info.value.source == "brave"
        assert exc_info.value.retry_after == 900

    @pytest.mark.asyncio
    async def test_raises_unavailable_on_500(self):
        def handler(_request):
            return httpx.Response(500)

        async with _make_client(handler) as client:
            with pytest.raises(SearchUnavailableError) as exc_info:
                await search_company_domain("Acme", None, client=client, api_key="key")
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_raises_unavailable_on_connect_error(self):
        def handler(request):
            raise httpx.ConnectError("down", request=request)

        async with _make_client(handler) as client:
            with pytest.raises(SearchUnavailableError) as exc_info:
                await search_company_domain("Acme", None, client=client, api_key="key")
        assert exc_info.value.source == "brave"

    @pytest.mark.asyncio
    async def test_raises_timeout_on_timeout(self):
        def handler(request):
            raise httpx.TimeoutException("timeout", request=request)

        async with _make_client(handler) as client:
            with pytest.raises(SearchTimeoutError) as exc_info:
                await search_company_domain("Acme", None, client=client, api_key="key")
        assert exc_info.value.source == "brave"

    @pytest.mark.asyncio
    async def test_returns_empty_when_web_results_missing(self):
        def handler(_request):
            return httpx.Response(200, json={"query": {"original": "acme"}})

        async with _make_client(handler) as client:
            candidates = await search_company_domain(
                "Acme", None, client=client, api_key="key"
            )

        assert candidates == []

    @pytest.mark.asyncio
    async def test_query_includes_city_and_site_oficial(self):
        seen_queries = []

        def handler(request):
            seen_queries.append(request.url.params.get("q", ""))
            return _brave_response([])

        async with _make_client(handler) as client:
            await search_company_domain(
                "Acme LTDA", "Campinas", client=client, api_key="key"
            )

        assert "Acme LTDA" in seen_queries[0]
        assert "Campinas" in seen_queries[0]
        assert "site oficial" in seen_queries[0]

    @pytest.mark.asyncio
    async def test_query_without_city(self):
        seen_queries = []

        def handler(request):
            seen_queries.append(request.url.params.get("q", ""))
            return _brave_response([])

        async with _make_client(handler) as client:
            await search_company_domain(
                "Acme LTDA", None, client=client, api_key="key"
            )

        assert "site oficial" in seen_queries[0]

    def test_directory_domains_not_empty(self):
        assert len(_DIRECTORY_DOMAINS) > 0
        assert "jusbrasil.com.br" in _DIRECTORY_DOMAINS
        assert "linkedin.com" in _DIRECTORY_DOMAINS

    @pytest.mark.asyncio
    async def test_raises_unavailable_on_json_decode_error(self):
        def handler(_request):
            return httpx.Response(200, content=b"not json", headers={"content-type": "text/html"})

        async with _make_client(handler) as client:
            with pytest.raises(SearchUnavailableError):
                await search_company_domain("Empresa", None, client=client, api_key="key")


class TestSearchWithQueries:
    @pytest.mark.asyncio
    async def test_tries_first_query_and_returns_on_success(self):
        call_count = 0

        def handler(_request):
            nonlocal call_count
            call_count += 1
            return _brave_response([_result("https://empresa.com.br")])

        queries = [
            SearchQuery('"12.345.678/0001-90"', 30, "cnpj_exact"),
            SearchQuery('"Empresa" Campinas', 15, "trade_name_city"),
        ]
        async with _make_client(handler) as client:
            candidates = await search_with_queries(queries, client=client, api_key="key")

        assert call_count == 1
        assert candidates[0].domain == "empresa.com.br"

    @pytest.mark.asyncio
    async def test_applies_confidence_bonus_from_query(self):
        def handler(_request):
            return _brave_response([_result("https://empresa.com.br")])

        queries = [SearchQuery('"12.345.678/0001-90"', 30, "cnpj_exact")]
        async with _make_client(handler) as client:
            candidates = await search_with_queries(queries, client=client, api_key="key")

        assert candidates[0].confidence == 55 + 30

    @pytest.mark.asyncio
    async def test_falls_back_to_next_query_when_first_empty(self):
        call_count = 0

        def handler(_request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _brave_response([])
            return _brave_response([_result("https://empresa2.com.br")])

        queries = [
            SearchQuery('"12.345.678/0001-90"', 30, "cnpj_exact"),
            SearchQuery('"Empresa" SP', 15, "trade_name_city"),
        ]
        async with _make_client(handler) as client:
            candidates = await search_with_queries(queries, client=client, api_key="key")

        assert call_count == 2
        assert candidates[0].domain == "empresa2.com.br"
        assert candidates[0].confidence == 55 + 15

    @pytest.mark.asyncio
    async def test_falls_back_when_first_returns_only_directories(self):
        call_count = 0

        def handler(_request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _brave_response([_result("https://jusbrasil.com.br/empresa/abc")])
            return _brave_response([_result("https://real-empresa.com.br")])

        queries = [
            SearchQuery('"cnpj"', 30, "cnpj_exact"),
            SearchQuery('"empresa"', 10, "trade_name"),
        ]
        async with _make_client(handler) as client:
            candidates = await search_with_queries(queries, client=client, api_key="key")

        assert call_count == 2
        assert candidates[0].domain == "real-empresa.com.br"

    @pytest.mark.asyncio
    async def test_returns_empty_when_all_queries_fail(self):
        def handler(_request):
            return _brave_response([])

        queries = [
            SearchQuery('"cnpj"', 30, "cnpj_exact"),
            SearchQuery('"name"', 10, "trade_name"),
        ]
        async with _make_client(handler) as client:
            candidates = await search_with_queries(queries, client=client, api_key="key")

        assert candidates == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_queries_empty(self):
        def handler(_request):
            return _brave_response([])

        async with _make_client(handler) as client:
            candidates = await search_with_queries([], client=client, api_key="key")

        assert candidates == []

    @pytest.mark.asyncio
    async def test_caps_confidence_at_100(self):
        def handler(_request):
            return _brave_response([_result("https://empresa.com.br")])

        queries = [SearchQuery('"cnpj"', 60, "cnpj_exact")]
        async with _make_client(handler) as client:
            candidates = await search_with_queries(queries, client=client, api_key="key")

        assert candidates[0].confidence <= 100
