from domain_discovery import (
    discover_domain_candidates,
    domains_from_brand_slugs,
    domains_from_rf_email,
    generate_brand_slugs,
    normalize_domain,
)
from rf_baseline import BaselineContact, normalize_rf_email


class TestDomainDiscovery:
    def test_normalize_domain_accepts_url_and_removes_www(self):
        assert normalize_domain("https://www.Example.com.br/contato") == "example.com.br"

    def test_normalize_domain_rejects_invalid_values(self):
        assert normalize_domain(None) is None
        assert normalize_domain("http://bad_domain") is None

    def test_generate_brand_slugs_prefers_trade_name_and_removes_suffixes(self):
        slugs = generate_brand_slugs("Empresa Acme Serviços LTDA", "Ácme Brasil")

        assert slugs == ["acmebrasil", "acme"]

    def test_domains_from_rf_email_uses_only_corporate_emails(self):
        candidate = domains_from_rf_email(normalize_rf_email("contato@acme.com.br"))[0]

        assert candidate.domain == "acme.com.br"
        assert candidate.confidence == 90
        assert domains_from_rf_email(normalize_rf_email("contato@gmail.com")) == []
        assert domains_from_rf_email(None) == []
        assert domains_from_rf_email(
            BaselineContact(
                contact_type="email",
                value="contato@bad_domain",
                normalized_value="contato@bad_domain",
                classification="corporate_domain",
            )
        ) == []

    def test_domains_from_brand_slugs_generates_all_tlds(self):
        candidates = domains_from_brand_slugs(["acme"])
        domains = [c.domain for c in candidates]

        assert domains == ["acme.com.br", "acme.net.br", "acme.org.br", "acme.ind.br", "acme.com"]

    def test_domains_from_brand_slugs_tld_confidence_order(self):
        candidates = domains_from_brand_slugs(["acme"])
        confidences = [c.confidence for c in candidates]

        assert confidences == [45, 42, 40, 35, 33]

    def test_discover_domain_candidates_dedupes_by_best_confidence(self):
        candidates = discover_domain_candidates(
            legal_name="Acme LTDA",
            trade_name="Acme",
            rf_email=normalize_rf_email("vendas@acme.com.br"),
        )

        assert candidates[0].domain == "acme.com.br"
        assert candidates[0].source == "rf_email_domain"
        assert [c.domain for c in candidates] == [
            "acme.com.br", "acme.net.br", "acme.org.br", "acme.ind.br", "acme.com"
        ]
