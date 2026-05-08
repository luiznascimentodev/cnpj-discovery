import pytest

from resolver.domain_verifier import (
    CANDIDATE_THRESHOLD,
    DomainScoreResult,
    VERIFIED_THRESHOLD,
    score_domain_evidence,
    update_domain_status,
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


class TestScoreDomainEvidence:
    def test_empty_html_with_minimal_inputs_is_rejected(self):
        result = score_domain_evidence("", domain="acme.com.br", cnpj="12345678000190")

        assert isinstance(result, DomainScoreResult)
        assert result.score == 0
        assert result.status == "rejected"

    def test_cnpj_exact_alone_yields_candidate(self):
        html = "Bem vindo. CNPJ 12.345.678/0001-90"

        result = score_domain_evidence(html, domain="acme.com.br", cnpj="12345678000190")

        assert "cnpj_exact" in result.signals
        assert result.score == 60
        assert result.status == "candidate"

    def test_rf_email_domain_match_adds_score(self):
        result = score_domain_evidence(
            "",
            domain="acme.com.br",
            cnpj="12345678000190",
            rf_email_domain="ACME.COM.BR",
        )

        assert "rf_email_domain_match" in result.signals
        assert result.score == 35

    def test_legal_name_exact_match(self):
        html = "Acme Industria Ltda - Soluções"

        result = score_domain_evidence(
            html,
            domain="acme.com.br",
            cnpj="00000000000000",
            legal_name="Acme Industria Ltda",
        )

        assert "legal_exact" in result.signals
        assert result.score == 30

    def test_fantasy_name_partial_match(self):
        html = "Servicos online da empresa Acme com qualidade"

        result = score_domain_evidence(
            html,
            domain="acme.com.br",
            cnpj="00000000000000",
            fantasy_name="Acme Brasil Servicos",
        )

        assert any(sig.startswith("fantasy") for sig in result.signals)
        assert result.score >= 12

    def test_fantasy_name_no_significant_tokens_returns_zero(self):
        html = "qualquer texto"

        result = score_domain_evidence(
            html,
            domain="acme.com.br",
            cnpj="00000000000000",
            fantasy_name="Me",
        )

        assert all(not sig.startswith("fantasy") for sig in result.signals)

    def test_fantasy_name_no_match_returns_zero(self):
        html = "Servicos diferentes sem nada"

        result = score_domain_evidence(
            html,
            domain="acme.com.br",
            cnpj="00000000000000",
            fantasy_name="Beta Gamma Delta",
        )

        assert all(not sig.startswith("fantasy") for sig in result.signals)

    def test_legal_name_only_whitespace_returns_zero(self):
        result = score_domain_evidence(
            "Acme aqui",
            domain="acme.com.br",
            cnpj="0",
            legal_name="   ",
        )

        assert all(not sig.startswith("legal") for sig in result.signals)

    def test_all_tokens_match_when_substring_does_not(self):
        html = "Industria moderna Acme Brasil Ltda em acao no setor"

        result = score_domain_evidence(
            html,
            domain="acme.com.br",
            cnpj="9999999999999999",
            legal_name="Acme Industria Brasil Ltda",
        )

        assert any(sig == "legal_all_tokens" for sig in result.signals)

    def test_cep_city_uf_phone_match(self):
        html = "CEP 01310-100, Sao Paulo SP, telefone (11) 9876-5432"

        result = score_domain_evidence(
            html,
            domain="acme.com.br",
            cnpj="00000000000000",
            cep="01310-100",
            city="São Paulo",
            uf="SP",
            rf_phone_normalized="1198765432",
        )

        assert "cep_match" in result.signals
        assert "city_match" in result.signals
        assert "uf_match" in result.signals
        assert "rf_phone_match" in result.signals
        assert result.score == 20 + 5 + 5 + 20

    def test_invalid_cep_does_not_match(self):
        result = score_domain_evidence(
            "",
            domain="acme.com.br",
            cnpj="00000000000000",
            cep="abc",
        )

        assert "cep_match" not in result.signals

    def test_directory_penalty_reduces_score(self):
        result = score_domain_evidence(
            "Acme Industria Ltda - 12.345.678/0001-90",
            domain="acme.com.br",
            cnpj="12345678000190",
            legal_name="Acme Industria Ltda",
            is_directory=True,
        )

        assert "directory_penalty" in result.signals
        assert result.score == 60 + 30 - 40

    def test_parked_penalty_drops_to_zero(self):
        result = score_domain_evidence(
            "Acme Industria",
            domain="acme.com.br",
            cnpj="00000000000000",
            legal_name="Acme Industria",
            is_parked=True,
        )

        assert "parked_penalty" in result.signals
        assert result.score == 0

    def test_score_capped_at_100(self):
        result = score_domain_evidence(
            "12.345.678/0001-90 ACME INDUSTRIA LTDA - "
            "ACME BRASIL CEP 01310-100 Sao Paulo SP "
            "telefone 11987654321",
            domain="acme.com.br",
            cnpj="12345678000190",
            legal_name="Acme Industria Ltda",
            fantasy_name="Acme Brasil",
            rf_email_domain="acme.com.br",
            rf_phone_normalized="11987654321",
            cep="01310100",
            city="Sao Paulo",
            uf="SP",
        )

        assert result.score == 100
        assert result.status == "verified"

    def test_status_rejected_when_score_below_candidate_threshold(self):
        result = score_domain_evidence("", domain="acme.com.br", cnpj="0")

        assert result.score == 0
        assert result.status == "rejected"

    def test_status_candidate_in_middle_band(self):
        result = score_domain_evidence(
            "Acme Industria Ltda - Sao Paulo SP - CEP 01310100",
            domain="acme.com.br",
            cnpj="9999999999999999",
            legal_name="Acme Industria Ltda",
            cep="01310100",
        )

        assert CANDIDATE_THRESHOLD <= result.score < VERIFIED_THRESHOLD
        assert result.status == "candidate"

    def test_status_verified_when_high_signals(self):
        result = score_domain_evidence(
            "12.345.678/0001-90 - Acme Industria Ltda",
            domain="acme.com.br",
            cnpj="12345678000190",
            legal_name="Acme Industria Ltda",
        )

        assert result.score >= VERIFIED_THRESHOLD
        assert result.status == "verified"


class TestUpdateDomainStatus:
    @pytest.mark.asyncio
    async def test_writes_score_and_status(self):
        conn = FakeConnection()

        await update_domain_status(
            FakePool(conn),
            cnpj_basico="12345678",
            cnpj_ordem="0001",
            cnpj_dv="90",
            domain="acme.com.br",
            score=92,
            status="verified",
        )

        assert conn.execute_calls[0][1] == ("12345678", "0001", "90", "acme.com.br", 92, "verified")
