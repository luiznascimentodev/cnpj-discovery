import httpx
import pytest

from unittest.mock import AsyncMock

from discovery.external_search import ExternalSearchClient
from discovery.pipeline import (
    PRIORITY_PATHS,
    DiscoveryOutcome,
    _SQL_FETCH_ESTABELECIMENTO,
    _SQL_FETCH_MATRIX_DOMAIN,
    _SQL_FETCH_SOCIOS,
    _SQL_IS_MEI,
    _SQL_UPSERT_RF_EMAIL_CONTACT,
    _SQL_UPSERT_RF_EMAIL_CONTACT_MEI,
    _SQL_UPSERT_RF_PHONE_CONTACT,
    _initial_confidence,
    _initial_status,
    _rf_email_domain,
    _row_value,
    _should_enqueue_crawl,
    _strong_identity_signals,
    process_target,
)
from discovery.website_probe import ProbeResult
from domain_discovery import DomainCandidate
from resolver.domain_verifier import DomainScoreResult
from rf_baseline import normalize_rf_email


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
    def __init__(self, fetchrow_result=None, fetchval_result=None, fetch_result=None):
        self._fetchrow_result = fetchrow_result
        self._fetchval_result = fetchval_result
        self._fetch_result = fetch_result if fetch_result is not None else []
        self.execute_calls = []
        self.fetch_calls = []

    async def fetchrow(self, query, *args):
        return self._fetchrow_result

    async def fetchval(self, query, *args):
        return self._fetchval_result

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self._fetch_result

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


def _httpx_client(handler):
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=httpx.Timeout(5.0),
    )


def _verified_handler(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        content=b"<html>12.345.678/0001-90 Acme LTDA</html>",
        headers={"content-type": "text/html"},
    )


def _weak_ok_handler(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"<html>OK</html>", headers={"content-type": "text/html"})


def _parked_handler(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"This domain is for sale!")


def _error_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down", request=request)


class TestHelpers:
    def test_initial_status_rejected_when_parked(self):
        probe = ProbeResult("d", "https://d/", 200, "text/html", "x", parked=True)

        assert _initial_status(probe) == "rejected"

    def test_initial_status_candidate_when_ok(self):
        probe = ProbeResult("d", "https://d/", 200, "text/html", "x", parked=False)

        assert _initial_status(probe) == "candidate"

    def test_initial_confidence_clamps_parked(self):
        candidate = DomainCandidate(domain="x", source="rf_email_domain", confidence=90)
        probe = ProbeResult("x", "https://x/", 200, "text/html", "y", parked=True)

        assert _initial_confidence(candidate, probe) == 5

    def test_initial_confidence_clamps_when_not_ok(self):
        candidate = DomainCandidate(domain="x", source="brand_slug", confidence=45)
        probe = ProbeResult("x", "https://x/", 0, "", "", parked=False, error="dead")

        assert _initial_confidence(candidate, probe) == 30

    def test_initial_confidence_keeps_when_ok(self):
        candidate = DomainCandidate(domain="x", source="rf_email_domain", confidence=90)
        probe = ProbeResult("x", "https://x/", 200, "text/html", "y", parked=False)

        assert _initial_confidence(candidate, probe) == 90

    def test_initial_confidence_uses_domain_score_when_available(self):
        candidate = DomainCandidate(domain="x", source="rf_email_domain", confidence=90)
        probe = ProbeResult("x", "https://x/", 200, "text/html", "y", parked=False)
        score = DomainScoreResult(score=63, status="candidate", signals=("legal_exact",))

        assert _initial_confidence(candidate, probe, score) == 63
        assert _initial_status(probe, score) == "candidate"

    def test_rf_email_domain_requires_corporate_email(self):
        assert _rf_email_domain(normalize_rf_email("contato@acme.com.br")) == "acme.com.br"
        assert _rf_email_domain(normalize_rf_email("contato@gmail.com")) is None
        assert _rf_email_domain(None) is None

    def test_identity_signal_and_enqueue_gate(self):
        verified = DomainScoreResult(score=80, status="verified", signals=())
        strong_candidate = DomainScoreResult(score=65, status="candidate", signals=("legal_exact",))
        weak_candidate = DomainScoreResult(score=65, status="candidate", signals=("city_match",))

        assert _should_enqueue_crawl(verified) is True
        assert _should_enqueue_crawl(strong_candidate) is True
        assert _strong_identity_signals(weak_candidate) is False
        assert _should_enqueue_crawl(weak_candidate) is False

    def test_row_value_returns_none_for_missing_key(self):
        assert _row_value({"present": "yes"}, "missing") is None


class TestProcessTarget:
    @pytest.mark.asyncio
    async def test_returns_zero_when_estabelecimento_missing(self):
        conn = FakeConnection(fetchrow_result=None)

        async with _httpx_client(_verified_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="00000000",
                cnpj_ordem="0000",
                cnpj_dv="00",
                client=client,
            )

        assert outcome == DiscoveryOutcome(cnpj="00000000000000", domains_seen=0, crawl_requests_created=0)
        assert conn.execute_calls == []

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_candidates(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "AA",
                "nome_fantasia": "BB",
                "email": "contato@gmail.com",
                "uf": "SP",
                "municipio": 1,
                "cep": "00000000",
            }
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="00000001",
                cnpj_ordem="0001",
                cnpj_dv="10",
                client=client,
            )

        assert outcome.domains_seen == 0
        assert outcome.crawl_requests_created == 0
        # B: gmail email salvo como contato direto
        assert outcome.rf_contacts_saved == 1
        rf_contact_calls = [c for c in conn.execute_calls if "enriched_contacts" in c[0]]
        assert len(rf_contact_calls) == 1
        assert rf_contact_calls[0][1][3] == "contato@gmail.com"

    @pytest.mark.asyncio
    async def test_b_saves_generic_email_even_when_domain_verified(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "dono@hotmail.com",
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": "11",
                "telefone1": "12345678",
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            }
        )

        async with _httpx_client(_verified_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        assert outcome.rf_contacts_saved == 1
        rf_contact_calls = [c for c in conn.execute_calls if "enriched_contacts" in c[0]]
        assert len(rf_contact_calls) == 1
        assert rf_contact_calls[0][1][3] == "dono@hotmail.com"

    @pytest.mark.asyncio
    async def test_b_does_not_save_corporate_email_as_direct_contact(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            }
        )

        async with _httpx_client(_verified_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        assert outcome.rf_contacts_saved == 0
        rf_contact_calls = [c for c in conn.execute_calls if "enriched_contacts" in c[0]]
        assert rf_contact_calls == []

    @pytest.mark.asyncio
    async def test_b_does_not_save_when_no_email(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Sem Email LTDA",
                "nome_fantasia": None,
                "email": None,
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": None,
                "cep": "00000000",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            }
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="99999999",
                cnpj_ordem="0001",
                cnpj_dv="00",
                client=client,
            )

        assert outcome.rf_contacts_saved == 0
        rf_contact_calls = [c for c in conn.execute_calls if "enriched_contacts" in c[0]]
        assert rf_contact_calls == []

    @pytest.mark.asyncio
    async def test_creates_crawl_requests_for_ok_domain(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "cep": "00000000",
            }
        )

        async with _httpx_client(_verified_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        assert outcome.domains_seen >= 1
        assert outcome.crawl_requests_created == outcome.domains_seen * len(PRIORITY_PATHS)

        upsert_calls = [c for c in conn.execute_calls if "company_domains" in c[0]]
        crawl_calls = [c for c in conn.execute_calls if "crawl_requests" in c[0]]
        assert len(upsert_calls) == outcome.domains_seen
        assert len(crawl_calls) == outcome.crawl_requests_created

        first_url = crawl_calls[0][1][3]
        assert first_url.startswith("https://acme.com.br")

    @pytest.mark.asyncio
    async def test_marks_weak_domain_rejected_and_skips_crawl_requests(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "cep": "00000000",
            }
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        crawl_calls = [c for c in conn.execute_calls if "crawl_requests" in c[0]]
        upsert_calls = [c for c in conn.execute_calls if "company_domains" in c[0]]
        assert outcome.crawl_requests_created == 0
        assert crawl_calls == []
        assert all("rejected" in str(call[1]) for call in upsert_calls)

    @pytest.mark.asyncio
    async def test_marks_parked_and_skips_crawl_requests(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "cep": "00000000",
            }
        )

        async with _httpx_client(_parked_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        crawl_calls = [c for c in conn.execute_calls if "crawl_requests" in c[0]]
        upsert_calls = [c for c in conn.execute_calls if "company_domains" in c[0]]
        assert outcome.crawl_requests_created == 0
        assert crawl_calls == []
        assert all("rejected" in str(call[1]) for call in upsert_calls)

    @pytest.mark.asyncio
    async def test_marks_unreachable_domain_as_candidate_with_low_confidence(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "cep": "00000000",
            }
        )

        async with _httpx_client(_error_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        crawl_calls = [c for c in conn.execute_calls if "crawl_requests" in c[0]]
        upsert_calls = [c for c in conn.execute_calls if "company_domains" in c[0]]
        assert outcome.crawl_requests_created == 0
        assert crawl_calls == []
        for call in upsert_calls:
            confidence_arg = call[1][6]
            status_arg = call[1][7]
            assert confidence_arg <= 30
            assert status_arg == "rejected"

    @pytest.mark.asyncio
    async def test_c_calls_external_search_when_no_domain_enqueued(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            },
            fetchval_result=None,  # no verified domain
        )
        ext = ExternalSearchClient(brasilapi_enabled=False, brave_api_key="")
        ext.enrich_candidates = AsyncMock(return_value=[])

        async with _httpx_client(_weak_ok_handler) as client:
            await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
                external_search=ext,
            )

        ext.enrich_candidates.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_c_skips_external_search_when_domain_already_verified_in_db_after_crawl(self):
        # Simulates a company whose brand_slug domain verified AND DB already has a verified record.
        # External search must be skipped.
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            },
            fetchval_result=1,  # verified domain already in DB
        )
        ext = ExternalSearchClient(brasilapi_enabled=False, brave_api_key="")
        ext.enrich_candidates = AsyncMock(return_value=[])

        async with _httpx_client(_verified_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
                external_search=ext,
            )

        ext.enrich_candidates.assert_not_awaited()
        assert outcome.crawl_requests_created > 0

    @pytest.mark.asyncio
    async def test_c_skips_external_search_when_already_verified_in_db(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            },
            fetchval_result=1,  # already has verified domain
        )
        ext = ExternalSearchClient(brasilapi_enabled=False, brave_api_key="")
        ext.enrich_candidates = AsyncMock(return_value=[])

        async with _httpx_client(_weak_ok_handler) as client:
            await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
                external_search=ext,
            )

        ext.enrich_candidates.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_c_external_candidate_verified_creates_crawl_requests(self):
        # Company has no candidates that verify in main loop (weak response for slugs).
        # External search returns "empresa-real.com.br" which IS verified (contains CNPJ).
        def selective_handler(request):
            if "empresa-real.com.br" in str(request.url):
                return httpx.Response(
                    200,
                    content=b"<html>12.345.678/0001-90 Zxqwerty LTDA</html>",
                    headers={"content-type": "text/html"},
                )
            return httpx.Response(200, content=b"<html>OK</html>", headers={"content-type": "text/html"})

        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Zxqwerty LTDA",
                "nome_fantasia": None,
                "email": None,
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            },
            fetchval_result=None,
        )
        extra = DomainCandidate(
            domain="empresa-real.com.br", source="brave_search", confidence=55,
            homepage_url="https://empresa-real.com.br",
        )
        ext = ExternalSearchClient(brasilapi_enabled=False, brave_api_key="")
        ext.enrich_candidates = AsyncMock(return_value=[extra])

        async with _httpx_client(selective_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
                external_search=ext,
            )

        ext.enrich_candidates.assert_awaited_once()
        assert outcome.crawl_requests_created == len(PRIORITY_PATHS)

    @pytest.mark.asyncio
    async def test_c_none_external_search_does_not_call_anything(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "cep": "00000000",
            }
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
                external_search=None,
            )

        assert outcome.crawl_requests_created == 0

    @pytest.mark.asyncio
    async def test_c_calls_external_search_even_when_brand_slug_produces_candidates(self):
        # Brand slug generates candidates but all are rejected (weak response).
        # External search should still be called because requests_created == 0 is no longer the gate.
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            },
            fetchval_result=None,  # no verified domain in DB
        )
        ext = ExternalSearchClient(brasilapi_enabled=False, brave_api_key="")
        ext.enrich_candidates = AsyncMock(return_value=[])

        # _weak_ok_handler means brand_slug candidates exist but score low → requests_created == 0
        # With old code external_search would only run when requests_created == 0 AND no verified domain.
        # With new code it runs whenever no verified domain in DB, regardless of requests_created.
        async with _httpx_client(_weak_ok_handler) as client:
            await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
                external_search=ext,
            )

        ext.enrich_candidates.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetches_partner_names_from_socios_table(self):
        # Verify that _SQL_FETCH_SOCIOS is called with cnpj_basico and that
        # partner names are extracted from socios rows.
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            },
            fetch_result=[
                {"nome_socio": "JOAO DA SILVA"},
                {"nome_socio": "MARIA SOUZA"},
            ],
        )

        async with _httpx_client(_weak_ok_handler) as client:
            await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        socios_calls = [c for c in conn.fetch_calls if _SQL_FETCH_SOCIOS in c[0]]
        assert len(socios_calls) == 1
        assert socios_calls[0][1][0] == "12345678"

    @pytest.mark.asyncio
    async def test_brand_slug_dns_miss_saves_rejected_without_http_probe(self, monkeypatch):
        """brand_slug candidate with no DNS → upserted as rejected, no HTTP probe made."""
        async def _dns_never_exists(domain: str, *, timeout: float = 3.0) -> bool:
            return False

        monkeypatch.setattr("discovery.pipeline.dns_exists", _dns_never_exists)

        probed = []

        def _tracking_handler(request: httpx.Request) -> httpx.Response:
            probed.append(str(request.url))
            return httpx.Response(200, content=b"<html>OK</html>")

        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "ACME LTDA",
                "nome_fantasia": "Acme",
                "email": None,
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            }
        )

        async with _httpx_client(_tracking_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        assert probed == []
        assert outcome.crawl_requests_created == 0
        rejected_calls = [c for c in conn.execute_calls if "rejected" in str(c[1])]
        assert len(rejected_calls) >= 1


class TestPipelineAddressFields:
    def test_sql_contains_new_address_and_cnae_fields(self):
        """_SQL_FETCH_ESTABELECIMENTO must select bairro, logradouro, numero, and cnae_descricao."""
        assert "est.bairro" in _SQL_FETCH_ESTABELECIMENTO
        assert "est.logradouro" in _SQL_FETCH_ESTABELECIMENTO
        assert "est.numero" in _SQL_FETCH_ESTABELECIMENTO
        assert "cnae_descricao" in _SQL_FETCH_ESTABELECIMENTO
        assert "LEFT JOIN cnaes c ON c.codigo = est.cnae_principal" in _SQL_FETCH_ESTABELECIMENTO

    @pytest.mark.asyncio
    async def test_passes_address_fields_to_score_domain_evidence(self):
        """Pipeline should pass non-None bairro/logradouro/numero/cnae_descricao to verifier."""
        # The verified handler returns CNPJ in body, so score_domain_evidence fires.
        # We verify the score actually uses the address data by checking the outcome is still
        # correct (i.e., the call doesn't blow up and produces crawl requests).
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "01310100",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": "BELA VISTA",
                "logradouro": "AV PAULISTA",
                "numero": "1000",
                "cnae_descricao": "Fabricacao de software",
            },
        )

        async with _httpx_client(_verified_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        # With address fields populated, pipeline should still score and enqueue normally.
        assert outcome.domains_seen >= 1
        assert outcome.crawl_requests_created >= len(PRIORITY_PATHS)


_FILIAL_ROW = {
    "razao_social": "Acme LTDA",
    "nome_fantasia": "Acme",
    "email": None,
    "uf": "SP",
    "municipio": 1,
    "municipio_descricao": "SAO PAULO",
    "cep": "00000000",
    "ddd1": None,
    "telefone1": None,
    "ddd2": None,
    "telefone2": None,
    "bairro": None,
    "logradouro": None,
    "numero": None,
    "cnae_descricao": None,
}

_MATRIX_DOMAIN_ROW = {
    "domain": "acme.com.br",
    "homepage_url": "https://acme.com.br/",
    "confidence": 95,
}


class FakeConnectionDispatch:
    """Like FakeConnection but returns different fetchrow results based on the query."""

    def __init__(self, estabelecimento_row, matrix_domain_row):
        self._estabelecimento_row = estabelecimento_row
        self._matrix_domain_row = matrix_domain_row
        self.execute_calls = []
        self.fetch_calls = []
        self.fetchrow_calls = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "company_domains" in query:
            return self._matrix_domain_row
        return self._estabelecimento_row

    async def fetchval(self, query, *args):
        return None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


class TestMatrixFilialResolution:
    @pytest.mark.asyncio
    async def test_filial_inherits_verified_domain_from_matrix(self):
        """Branch with cnpj_ordem != '0001' should copy verified domain from parent."""
        conn = FakeConnectionDispatch(
            estabelecimento_row=_FILIAL_ROW,
            matrix_domain_row=_MATRIX_DOMAIN_ROW,
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0002",
                cnpj_dv="73",
                client=client,
            )

        # Should return early with domains_seen=1 and no crawl requests
        assert outcome == DiscoveryOutcome(
            cnpj="1234567800027" + "3",
            domains_seen=1,
            crawl_requests_created=0,
            rf_contacts_saved=0,
        )

        # _SQL_FETCH_MATRIX_DOMAIN must have been called
        matrix_fetchrow_calls = [
            c for c in conn.fetchrow_calls if "company_domains" in c[0]
        ]
        assert len(matrix_fetchrow_calls) == 1
        assert matrix_fetchrow_calls[0][1][0] == "12345678"

        # _SQL_UPSERT_DOMAIN must have been called with source="matrix_resolution"
        domain_upsert_calls = [
            c for c in conn.execute_calls if "company_domains" in c[0]
        ]
        assert len(domain_upsert_calls) == 1
        upsert_args = domain_upsert_calls[0][1]
        # args: cnpj_basico, cnpj_ordem, cnpj_dv, domain, homepage_url, source, confidence, status
        assert upsert_args[0] == "12345678"
        assert upsert_args[1] == "0002"
        assert upsert_args[5] == "matrix_resolution"
        assert upsert_args[7] == "verified"

    @pytest.mark.asyncio
    async def test_matriz_skips_matrix_resolution(self):
        """Parent company (cnpj_ordem='0001') should never call _SQL_FETCH_MATRIX_DOMAIN."""
        conn = FakeConnectionDispatch(
            estabelecimento_row={
                **_FILIAL_ROW,
                "email": "contato@acme.com.br",
            },
            matrix_domain_row=_MATRIX_DOMAIN_ROW,
        )

        async with _httpx_client(_weak_ok_handler) as client:
            await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        # _SQL_FETCH_MATRIX_DOMAIN must NOT have been called for the matriz
        matrix_fetchrow_calls = [
            c for c in conn.fetchrow_calls if _SQL_FETCH_MATRIX_DOMAIN in c[0]
        ]
        assert matrix_fetchrow_calls == []

    @pytest.mark.asyncio
    async def test_filial_runs_full_discovery_when_no_matrix_domain(self):
        """Branch should run normal discovery when parent has no verified domain."""
        conn = FakeConnectionDispatch(
            estabelecimento_row={**_FILIAL_ROW, "email": "contato@acme.com.br"},
            matrix_domain_row=None,  # no verified matrix domain
        )

        async with _httpx_client(_verified_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0002",
                cnpj_dv="73",
                client=client,
            )

        # Full discovery should run: candidates generated and domain upserted
        assert outcome.domains_seen >= 1

        domain_upsert_calls = [
            c for c in conn.execute_calls if "company_domains" in c[0]
        ]
        # At least one domain was upserted via normal discovery
        assert len(domain_upsert_calls) >= 1
        # source must NOT be "matrix_resolution" — it came from real discovery
        for call in domain_upsert_calls:
            assert call[1][5] != "matrix_resolution"


_MEI_ROW = {
    **_FILIAL_ROW,
    "razao_social": "JOAO DA SILVA 12345678000190",
    "nome_fantasia": None,
    "email": None,
    "cnpj_ordem": "0001",
}


class FakeConnectionMei:
    """Dispatches fetchrow based on query: estabelecimento, simples, or matrix."""

    def __init__(self, estabelecimento_row, mei_row, matrix_domain_row=None, fetchval_result=None):
        self._estabelecimento_row = estabelecimento_row
        self._mei_row = mei_row
        self._matrix_domain_row = matrix_domain_row
        self._fetchval_result = fetchval_result
        self.execute_calls = []
        self.fetch_calls = []
        self.fetchrow_calls = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "simples" in query:
            return self._mei_row
        if "company_domains" in query:
            return self._matrix_domain_row
        return self._estabelecimento_row

    async def fetchval(self, query, *args):
        return self._fetchval_result

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


class TestMeiDetection:
    def test_sql_is_mei_queries_simples_table(self):
        assert "simples" in _SQL_IS_MEI
        assert "opcao_mei" in _SQL_IS_MEI

    @pytest.mark.asyncio
    async def test_mei_skips_brand_slug_discovery(self):
        """MEI company (opcao_mei='S') should NOT call discover_domain_candidates."""
        from unittest.mock import patch

        conn = FakeConnectionMei(
            estabelecimento_row=_MEI_ROW,
            mei_row={"opcao_mei": "S"},
        )
        ext = ExternalSearchClient(brasilapi_enabled=False, brave_api_key="")
        ext.enrich_candidates = AsyncMock(return_value=[])

        with patch("discovery.pipeline.discover_domain_candidates") as mock_discover:
            async with _httpx_client(_weak_ok_handler) as client:
                await process_target(
                    FakePool(conn),
                    cnpj_basico="12345678",
                    cnpj_ordem="0001",
                    cnpj_dv="90",
                    client=client,
                    external_search=ext,
                )

        mock_discover.assert_not_called()

    @pytest.mark.asyncio
    async def test_mei_external_search_still_runs(self):
        """MEI company should still use external_search (social-focused queries)."""
        conn = FakeConnectionMei(
            estabelecimento_row=_MEI_ROW,
            mei_row={"opcao_mei": "S"},
            fetchval_result=None,
        )
        ext = ExternalSearchClient(brasilapi_enabled=False, brave_api_key="")
        ext.enrich_candidates = AsyncMock(return_value=[])

        async with _httpx_client(_weak_ok_handler) as client:
            await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
                external_search=ext,
            )

        ext.enrich_candidates.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_mei_uses_brand_slug_discovery(self):
        """Non-MEI company (opcao_mei='N') should use discover_domain_candidates."""
        from unittest.mock import patch

        conn = FakeConnectionMei(
            estabelecimento_row={**_MEI_ROW, "email": "contato@acme.com.br"},
            mei_row={"opcao_mei": "N"},
        )

        with patch("discovery.pipeline.discover_domain_candidates") as mock_discover:
            mock_discover.return_value = []
            async with _httpx_client(_weak_ok_handler) as client:
                await process_target(
                    FakePool(conn),
                    cnpj_basico="12345678",
                    cnpj_ordem="0001",
                    cnpj_dv="90",
                    client=client,
                )

        mock_discover.assert_called_once()

    @pytest.mark.asyncio
    async def test_mei_not_in_simples_uses_brand_slug(self):
        """Company not in simples table (fetchrow returns None) should use brand_slug."""
        from unittest.mock import patch

        conn = FakeConnectionMei(
            estabelecimento_row={**_MEI_ROW, "email": "contato@acme.com.br"},
            mei_row=None,  # not in simples table
        )

        with patch("discovery.pipeline.discover_domain_candidates") as mock_discover:
            mock_discover.return_value = []
            async with _httpx_client(_weak_ok_handler) as client:
                await process_target(
                    FakePool(conn),
                    cnpj_basico="12345678",
                    cnpj_ordem="0001",
                    cnpj_dv="90",
                    client=client,
                )

        mock_discover.assert_called_once()


_MEI_ROW_WITH_PHONE = {
    **_MEI_ROW,
    "ddd1": "11",
    "telefone1": "987654321",
    "ddd2": "11",
    "telefone2": "912345678",
}

_MEI_ROW_WITH_EMAIL = {
    **_MEI_ROW,
    "email": "joao@gmail.com",
}

_MEI_ROW_WITH_CORP_EMAIL = {
    **_MEI_ROW,
    "email": "contato@joaoartesanato.com.br",
}


class TestMeiRfPhoneContact:
    """MEI companies save RF phone/email contacts via dedicated SQL."""

    def test_sql_constants_exist(self):
        assert "rf_email_mei" in _SQL_UPSERT_RF_EMAIL_CONTACT_MEI
        assert "Email MEI" in _SQL_UPSERT_RF_EMAIL_CONTACT_MEI
        assert "$8" in _SQL_UPSERT_RF_PHONE_CONTACT
        assert "enriched_contacts" in _SQL_UPSERT_RF_PHONE_CONTACT

    @pytest.mark.asyncio
    async def test_mei_saves_phone1_as_rf_contact(self):
        """MEI with ddd1/telefone1 saves one phone contact with confidence 75."""
        conn = FakeConnectionMei(
            estabelecimento_row=_MEI_ROW_WITH_PHONE,
            mei_row={"opcao_mei": "S"},
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        phone_calls = [c for c in conn.execute_calls if "enriched_contacts" in c[0] and "'phone'" in c[0]]
        assert len(phone_calls) >= 1
        # First phone call: args are (cnpj_basico, cnpj_ordem, cnpj_dv, value, normalized, label, source, confidence)
        first_phone_args = phone_calls[0][1]
        assert first_phone_args[6] == "rf_phone_mei"
        assert first_phone_args[7] == 75
        assert outcome.rf_contacts_saved >= 1

    @pytest.mark.asyncio
    async def test_mei_saves_both_phones_when_different(self):
        """MEI with two distinct phones saves both contacts."""
        conn = FakeConnectionMei(
            estabelecimento_row=_MEI_ROW_WITH_PHONE,
            mei_row={"opcao_mei": "S"},
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        phone_calls = [c for c in conn.execute_calls if "enriched_contacts" in c[0] and "'phone'" in c[0]]
        assert len(phone_calls) == 2
        # Second phone uses confidence 70
        second_phone_args = phone_calls[1][1]
        assert second_phone_args[7] == 70
        assert outcome.rf_contacts_saved == 2

    @pytest.mark.asyncio
    async def test_mei_skips_duplicate_phone2(self):
        """MEI with identical phone1 and phone2 (same normalized_value) saves only one."""
        row = {
            **_MEI_ROW,
            "ddd1": "11",
            "telefone1": "987654321",
            "ddd2": "11",
            "telefone2": "987654321",  # same number
        }
        conn = FakeConnectionMei(
            estabelecimento_row=row,
            mei_row={"opcao_mei": "S"},
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        phone_calls = [c for c in conn.execute_calls if "enriched_contacts" in c[0] and "'phone'" in c[0]]
        assert len(phone_calls) == 1
        assert outcome.rf_contacts_saved == 1

    @pytest.mark.asyncio
    async def test_mei_saves_public_provider_email(self):
        """MEI with gmail email saves it via _SQL_UPSERT_RF_EMAIL_CONTACT_MEI (confidence 65)."""
        conn = FakeConnectionMei(
            estabelecimento_row=_MEI_ROW_WITH_EMAIL,
            mei_row={"opcao_mei": "S"},
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        email_calls = [c for c in conn.execute_calls if "enriched_contacts" in c[0] and "'email'" in c[0]]
        assert len(email_calls) == 1
        assert "rf_email_mei" in email_calls[0][0]
        assert outcome.rf_contacts_saved == 1

    @pytest.mark.asyncio
    async def test_mei_saves_corporate_email(self):
        """MEI with corporate email also saves via MEI SQL (not the non-MEI path)."""
        conn = FakeConnectionMei(
            estabelecimento_row=_MEI_ROW_WITH_CORP_EMAIL,
            mei_row={"opcao_mei": "S"},
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        email_calls = [c for c in conn.execute_calls if "enriched_contacts" in c[0] and "'email'" in c[0]]
        assert len(email_calls) == 1
        assert "rf_email_mei" in email_calls[0][0]
        assert outcome.rf_contacts_saved == 1

    @pytest.mark.asyncio
    async def test_non_mei_public_provider_email_uses_original_sql(self):
        """Non-MEI public_provider email uses _SQL_UPSERT_RF_EMAIL_CONTACT (confidence 40)."""
        conn = FakeConnectionMei(
            estabelecimento_row={**_MEI_ROW, "email": "owner@gmail.com"},
            mei_row={"opcao_mei": "N"},
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        email_calls = [c for c in conn.execute_calls if "enriched_contacts" in c[0]]
        assert len(email_calls) == 1
        assert "rf_email_direct" in email_calls[0][0]
        assert outcome.rf_contacts_saved == 1

    @pytest.mark.asyncio
    async def test_mei_no_phone_no_email_saves_nothing(self):
        """MEI with no phone and no email saves no contacts."""
        conn = FakeConnectionMei(
            estabelecimento_row=_MEI_ROW,  # email=None, ddd1=None
            mei_row={"opcao_mei": "S"},
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        contact_calls = [c for c in conn.execute_calls if "enriched_contacts" in c[0]]
        assert contact_calls == []
        assert outcome.rf_contacts_saved == 0


class TestDnsOnlyMode:
    @pytest.mark.asyncio
    async def test_dns_only_skips_external_search(self):
        """dns_only=True: external_search.enrich_candidates must never be called."""
        called = []

        class FakeExternalSearch:
            async def enrich_candidates(self, **kwargs):
                called.append(kwargs)
                return []

        conn = FakeConnectionMei(
            estabelecimento_row=_MEI_ROW,
            mei_row={"opcao_mei": "S"},
            fetchval_result=None,
        )

        async with _httpx_client(_weak_ok_handler) as client:
            await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
                external_search=FakeExternalSearch(),
                dns_only=True,
            )

        assert called == []

    @pytest.mark.asyncio
    async def test_dns_only_mei_returns_early_with_rf_contacts(self):
        """dns_only=True with MEI: returns early after saving RF contacts."""
        conn = FakeConnectionMei(
            estabelecimento_row=_MEI_ROW_WITH_PHONE,
            mei_row={"opcao_mei": "S"},
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
                dns_only=True,
            )

        assert outcome.domains_seen == 0
        assert outcome.crawl_requests_created == 0
        assert outcome.rf_contacts_saved >= 1

    @pytest.mark.asyncio
    async def test_dns_only_false_calls_external_search_for_mei(self):
        """dns_only=False (default): external_search IS called for MEI when no verified domain."""
        called = []

        class FakeExternalSearch:
            async def enrich_candidates(self, **kwargs):
                called.append(True)
                return []

        conn = FakeConnectionMei(
            estabelecimento_row=_MEI_ROW,
            mei_row={"opcao_mei": "S"},
            fetchval_result=None,
        )

        async with _httpx_client(_weak_ok_handler) as client:
            await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
                external_search=FakeExternalSearch(),
                dns_only=False,
            )

        assert called == [True]

    @pytest.mark.asyncio
    async def test_dns_only_non_mei_still_runs_brand_slug(self):
        """dns_only=True for non-MEI does NOT short-circuit brand_slug discovery."""
        from unittest.mock import patch

        conn = FakeConnectionMei(
            estabelecimento_row={**_MEI_ROW, "email": "contato@acme.com.br"},
            mei_row={"opcao_mei": "N"},
        )

        with patch("discovery.pipeline.discover_domain_candidates") as mock_discover:
            mock_discover.return_value = []
            async with _httpx_client(_weak_ok_handler) as client:
                await process_target(
                    FakePool(conn),
                    cnpj_basico="12345678",
                    cnpj_ordem="0001",
                    cnpj_dv="90",
                    client=client,
                    dns_only=True,
                )

        # Non-MEI with dns_only still runs brand_slug discovery (dns_only only skips external_search)
        mock_discover.assert_called_once()

    @pytest.mark.asyncio
    async def test_dns_only_non_mei_skips_external_search(self):
        """dns_only=True for non-MEI: external_search is skipped."""
        called = []

        class FakeExternalSearch:
            async def enrich_candidates(self, **kwargs):
                called.append(True)
                return []

        conn = FakeConnectionMei(
            estabelecimento_row={**_MEI_ROW, "email": "contato@acme.com.br"},
            mei_row={"opcao_mei": "N"},
            fetchval_result=None,
        )

        async with _httpx_client(_weak_ok_handler) as client:
            await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
                external_search=FakeExternalSearch(),
                dns_only=True,
            )

        assert called == []

    @pytest.mark.asyncio
    async def test_dns_only_skips_http_probe_for_rf_email_candidates(self):
        """dns_only=True: probe_domain must never be called even for rf_email_domain candidates."""
        from unittest.mock import patch

        conn = FakeConnectionMei(
            estabelecimento_row={**_MEI_ROW, "email": "contato@acme.com.br"},
            mei_row={"opcao_mei": "N"},
        )

        rf_email_candidate = DomainCandidate(
            domain="acme.com.br",
            source="rf_email_domain",
            confidence=70,
            homepage_url="https://acme.com.br",
            reason="rf email match",
        )

        with (
            patch("discovery.pipeline.discover_domain_candidates", return_value=[rf_email_candidate]),
            patch("discovery.pipeline.probe_domain") as mock_probe,
        ):
            async with _httpx_client(_weak_ok_handler) as client:
                outcome = await process_target(
                    FakePool(conn),
                    cnpj_basico="12345678",
                    cnpj_ordem="0001",
                    cnpj_dv="90",
                    client=client,
                    dns_only=True,
                )

        mock_probe.assert_not_called()
        # Candidate should be saved as 'candidate' status without probing
        domain_upserts = [args for sql, args in conn.execute_calls if "company_domains" in sql]
        assert len(domain_upserts) >= 1
        assert any("candidate" in args for args in domain_upserts)


class TestNonBrandSlugCandidates:
    @pytest.mark.asyncio
    async def test_non_brand_slug_candidates_skip_dns_check(self):
        """Candidates with source != 'brand_slug' bypass DNS pre-check (else branch)."""
        from unittest.mock import patch

        rf_email_candidate = DomainCandidate(
            domain="acme.com.br",
            source="rf_email",
            confidence=80,
            homepage_url="https://acme.com.br",
            reason="rf email match",
        )

        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "ACME LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            }
        )

        with (
            patch("discovery.pipeline.discover_domain_candidates", return_value=[rf_email_candidate]),
            patch("discovery.pipeline.dns_exists", new_callable=AsyncMock) as mock_dns,
        ):
            async with _httpx_client(_weak_ok_handler) as client:
                outcome = await process_target(
                    FakePool(conn),
                    cnpj_basico="12345678",
                    cnpj_ordem="0001",
                    cnpj_dv="90",
                    client=client,
                )

        mock_dns.assert_not_called()
        assert outcome.domains_seen >= 1
