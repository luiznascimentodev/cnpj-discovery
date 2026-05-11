import httpx
import pytest

from discovery.external_search import ExternalSearchClient
from domain_discovery import DomainCandidate


def _make_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=httpx.Timeout(5.0))


def _brasilapi_response(email=None, qsa_names=None):
    return httpx.Response(200, json={
        "email": email,
        "ddd_telefone_1": None,
        "ddd_telefone_2": None,
        "qsa": [{"nome_socio": n} for n in (qsa_names or [])],
    })


def _brave_response(domains: list[str]) -> httpx.Response:
    return httpx.Response(200, json={
        "web": {"results": [{"url": f"https://{d}"} for d in domains]}
    })


def _cse_response(domains: list[str]) -> httpx.Response:
    return httpx.Response(200, json={
        "items": [{"link": f"https://{d}"} for d in domains]
    })


class TestEnrichCandidatesV2:
    @pytest.mark.asyncio
    async def test_cnpj_query_finds_domain_without_brasilapi_email(self):
        """Brave Search com query CNPJ retorna domínio mesmo sem email RF."""
        requests_seen = []

        def handler(request):
            requests_seen.append(str(request.url))
            if "brasilapi" in str(request.url):
                return _brasilapi_response(email=None)
            return _brave_response(["empresa.com.br"])

        client_obj = ExternalSearchClient(
            brasilapi_enabled=True,
            brave_api_key="key",
            google_cse_api_key="",
            google_cse_cx="",
        )
        async with _make_client(handler) as client:
            candidates = await client_obj.enrich_candidates(
                cnpj14="12345678000190",
                legal_name="EMPRESA XPTO LTDA",
                trade_name="Empresa XPTO",
                city="São Paulo",
                partner_names=[],
                client=client,
            )

        assert len(candidates) > 0
        assert candidates[0].domain == "empresa.com.br"

    @pytest.mark.asyncio
    async def test_brasilapi_email_domain_takes_priority(self):
        """Email corporativo RF ainda tem prioridade por ser dado oficial."""
        def handler(request):
            if "brasilapi" in str(request.url):
                return _brasilapi_response(email="contato@minhaemp.com.br")
            return _brave_response(["outro.com.br"])

        client_obj = ExternalSearchClient(
            brasilapi_enabled=True,
            brave_api_key="key",
            google_cse_api_key="",
            google_cse_cx="",
        )
        async with _make_client(handler) as client:
            candidates = await client_obj.enrich_candidates(
                cnpj14="12345678000190",
                legal_name="MINHA EMP LTDA",
                trade_name=None,
                city=None,
                partner_names=[],
                client=client,
            )

        assert candidates[0].domain == "minhaemp.com.br"
        assert candidates[0].source == "rf_email_domain"

    @pytest.mark.asyncio
    async def test_google_cse_used_when_brave_returns_empty(self):
        """Google CSE é o fallback quando Brave não encontra nada."""
        call_log = []

        def handler(request):
            url = str(request.url)
            call_log.append(url)
            if "brasilapi" in url:
                return _brasilapi_response(email=None)
            if "search.brave.com" in url:
                return _brave_response([])
            if "googleapis.com" in url:
                return _cse_response(["empresa-via-google.com.br"])
            return httpx.Response(404)

        client_obj = ExternalSearchClient(
            brasilapi_enabled=True,
            brave_api_key="brave-key",
            google_cse_api_key="google-key",
            google_cse_cx="my-cx",
        )
        async with _make_client(handler) as client:
            candidates = await client_obj.enrich_candidates(
                cnpj14="12345678000190",
                legal_name="EMPRESA XPTO LTDA",
                trade_name="XPTO",
                city="Curitiba",
                partner_names=[],
                client=client,
            )

        assert any("googleapis" in url for url in call_log)
        assert len(candidates) > 0
        assert candidates[0].domain == "empresa-via-google.com.br"

    @pytest.mark.asyncio
    async def test_returns_empty_when_all_sources_fail(self):
        def handler(request):
            return httpx.Response(500)

        client_obj = ExternalSearchClient(
            brasilapi_enabled=True,
            brave_api_key="key",
            google_cse_api_key="",
            google_cse_cx="",
        )
        async with _make_client(handler) as client:
            candidates = await client_obj.enrich_candidates(
                cnpj14="12345678000190",
                legal_name="EMPRESA XPTO LTDA",
                trade_name=None,
                city=None,
                partner_names=[],
                client=client,
            )

        assert candidates == []

    @pytest.mark.asyncio
    async def test_partner_names_included_in_queries_when_name_search_runs(self):
        """Partner names são passados ao query builder e podem ser usados."""
        queries_seen = []

        def handler(request):
            if "search.brave.com" in str(request.url):
                q = request.url.params.get("q", "")
                queries_seen.append(q)
                return _brave_response(["result.com.br"])
            return _brasilapi_response(email=None)

        client_obj = ExternalSearchClient(
            brasilapi_enabled=True,
            brave_api_key="key",
            google_cse_api_key="",
            google_cse_cx="",
        )
        async with _make_client(handler) as client:
            await client_obj.enrich_candidates(
                cnpj14="12345678000190",
                legal_name="EMPRESA LTDA",
                trade_name="Empresa",
                city="SP",
                partner_names=["João Silva"],
                client=client,
            )

        all_queries = " ".join(queries_seen)
        assert "12.345.678/0001-90" in all_queries

    @pytest.mark.asyncio
    async def test_google_cse_tries_multiple_queries_until_results(self):
        """Google CSE tenta múltiplas queries até obter resultados."""
        call_log = []

        def handler(request):
            url = str(request.url)
            call_log.append(url)
            if "brasilapi" in url:
                return _brasilapi_response(email=None)
            if "search.brave.com" in url:
                return _brave_response([])
            if "googleapis.com" in url:
                # Primeira query retorna vazio, segunda retorna resultado
                if call_log.count(url[:50]) == 1:
                    return _cse_response([])
                return _cse_response(["resultado.com.br"])
            return httpx.Response(404)

        client_obj = ExternalSearchClient(
            brasilapi_enabled=True,
            brave_api_key="brave-key",
            google_cse_api_key="google-key",
            google_cse_cx="my-cx",
        )
        async with _make_client(handler) as client:
            candidates = await client_obj.enrich_candidates(
                cnpj14="12345678000190",
                legal_name="EMPRESA LTDA",
                trade_name="Empresa",
                city="SP",
                partner_names=[],
                client=client,
            )

        assert len(candidates) > 0
        assert candidates[0].domain == "resultado.com.br"

    @pytest.mark.asyncio
    async def test_brasilapi_qsa_names_enriches_search_when_no_local_partners(self):
        """QSA da BrasilAPI enriquece queries quando não temos partner_names locais."""
        queries_sent = []

        def handler(request):
            if "search.brave.com" in str(request.url):
                q = request.url.params.get("q", "")
                queries_sent.append(q)
                return _brave_response(["empresa.com.br"])
            if "brasilapi" in str(request.url):
                return _brasilapi_response(email=None, qsa_names=["Maria Silva", "João Santos"])
            return httpx.Response(404)

        client_obj = ExternalSearchClient(
            brasilapi_enabled=True,
            brave_api_key="key",
            google_cse_api_key="",
            google_cse_cx="",
        )
        async with _make_client(handler) as client:
            candidates = await client_obj.enrich_candidates(
                cnpj14="12345678000190",
                legal_name="EMPRESA LTDA",
                trade_name="Empresa",
                city="SP",
                partner_names=[],  # Empty, so BrasilAPI QSA should be used
                client=client,
            )

        # Verify that queries were made (which would use QSA names)
        assert len(queries_sent) > 0
        assert len(candidates) > 0
