import httpx
import pytest

from discovery.google_cse import search_google_cse
from discovery.search_queries import SearchQuery


def _make_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=httpx.Timeout(5.0))


def _cse_response(items: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"items": items})


def _item(link: str, title: str = "Empresa") -> dict:
    return {"link": link, "title": title, "displayLink": link}


class TestSearchGoogleCse:
    @pytest.mark.asyncio
    async def test_returns_candidates_for_valid_results(self):
        def handler(_request):
            return _cse_response([
                _item("https://acmebrasil.com.br"),
                _item("https://acme.com"),
            ])

        query = SearchQuery('"12.345.678/0001-90"', 30, "cnpj_exact")
        async with _make_client(handler) as client:
            candidates = await search_google_cse(query, client=client, api_key="k", cx="cx")

        assert len(candidates) == 2
        assert candidates[0].domain == "acmebrasil.com.br"
        assert candidates[0].source == "google_cse"
        assert candidates[0].confidence == min(55 + 30, 100)

    @pytest.mark.asyncio
    async def test_filters_directory_domains(self):
        def handler(_request):
            return _cse_response([
                _item("https://jusbrasil.com.br/empresa/acme"),
                _item("https://acmebrasil.com.br"),
            ])

        query = SearchQuery('"Acme"', 10, "trade_name")
        async with _make_client(handler) as client:
            candidates = await search_google_cse(query, client=client, api_key="k", cx="cx")

        domains = [c.domain for c in candidates]
        assert "jusbrasil.com.br" not in domains
        assert "acmebrasil.com.br" in domains

    @pytest.mark.asyncio
    async def test_returns_empty_on_400(self):
        def handler(_request):
            return httpx.Response(400, json={"error": {"code": 400}})

        query = SearchQuery('"test"', 10, "trade_name")
        async with _make_client(handler) as client:
            candidates = await search_google_cse(query, client=client, api_key="k", cx="cx")

        assert candidates == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_http_error(self):
        def handler(request):
            raise httpx.ConnectError("down", request=request)

        query = SearchQuery('"test"', 10, "trade_name")
        async with _make_client(handler) as client:
            candidates = await search_google_cse(query, client=client, api_key="k", cx="cx")

        assert candidates == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_items(self):
        def handler(_request):
            return httpx.Response(200, json={"searchInformation": {"totalResults": "0"}})

        query = SearchQuery('"test"', 10, "trade_name")
        async with _make_client(handler) as client:
            candidates = await search_google_cse(query, client=client, api_key="k", cx="cx")

        assert candidates == []

    @pytest.mark.asyncio
    async def test_query_params_sent_correctly(self):
        seen_params = {}

        def handler(request):
            seen_params.update(dict(request.url.params))
            return _cse_response([])

        query = SearchQuery('"12.345.678/0001-90"', 30, "cnpj_exact")
        async with _make_client(handler) as client:
            await search_google_cse(
                query, client=client, api_key="mykey", cx="mycx",
                base_url="https://www.googleapis.com/customsearch/v1"
            )

        assert seen_params["key"] == "mykey"
        assert seen_params["cx"] == "mycx"
        assert seen_params["q"] == '"12.345.678/0001-90"'
        assert seen_params["gl"] == "br"
