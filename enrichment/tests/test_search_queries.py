import pytest
from discovery.search_queries import SearchQuery, build_search_queries, build_search_queries_mei, format_cnpj14


class TestFormatCnpj14:
    def test_formats_14_digit_cnpj(self):
        assert format_cnpj14("12345678000190") == "12.345.678/0001-90"

    def test_returns_raw_if_not_14_digits(self):
        assert format_cnpj14("123") == "123"

    def test_returns_raw_if_not_all_digits(self):
        assert format_cnpj14("1234567800019X") == "1234567800019X"


class TestBuildSearchQueries:
    def test_cnpj_query_is_first_and_highest_bonus(self):
        queries = build_search_queries(
            cnpj14="12345678000190",
            legal_name="ACME LTDA",
            trade_name="Acme Brasil",
            city="São Paulo",
            partner_names=[],
        )
        assert queries[0].text == '"12.345.678/0001-90"'
        assert queries[0].confidence_bonus == 30
        assert queries[0].reason == "cnpj_exact"

    def test_trade_name_city_query_included(self):
        queries = build_search_queries(
            cnpj14="12345678000190",
            legal_name="ACME LTDA",
            trade_name="Acme Brasil",
            city="Campinas",
            partner_names=[],
        )
        texts = [q.text for q in queries]
        assert any("Acme Brasil" in t and "Campinas" in t for t in texts)

    def test_legal_name_query_strips_suffixes(self):
        queries = build_search_queries(
            cnpj14="12345678000190",
            legal_name="PADARIA DO JOSE EIRELI",
            trade_name=None,
            city="Belo Horizonte",
            partner_names=[],
        )
        texts = [q.text for q in queries]
        assert any("PADARIA DO JOSE" in t for t in texts)
        assert not any("EIRELI" in t for t in texts)

    def test_partner_name_query_included_when_provided(self):
        queries = build_search_queries(
            cnpj14="12345678000190",
            legal_name="TECH LTDA",
            trade_name=None,
            city="Rio de Janeiro",
            partner_names=["João da Silva"],
        )
        texts = [q.text for q in queries]
        assert any("João da Silva" in t for t in texts)

    def test_deduplicates_when_trade_equals_legal(self):
        queries = build_search_queries(
            cnpj14="12345678000190",
            legal_name="ACME LTDA",
            trade_name="ACME LTDA",
            city="SP",
            partner_names=[],
        )
        texts = [q.text for q in queries]
        assert len(texts) == len(set(texts))

    def test_returns_at_least_cnpj_query_when_names_missing(self):
        queries = build_search_queries(
            cnpj14="12345678000190",
            legal_name=None,
            trade_name=None,
            city=None,
            partner_names=[],
        )
        assert len(queries) >= 1
        assert queries[0].reason == "cnpj_exact"

    def test_queries_ordered_by_confidence_bonus_desc(self):
        queries = build_search_queries(
            cnpj14="12345678000190",
            legal_name="EMPRESA XPTO LTDA",
            trade_name="XPTO Digital",
            city="Curitiba",
            partner_names=["Maria Souza"],
        )
        bonuses = [q.confidence_bonus for q in queries]
        assert bonuses == sorted(bonuses, reverse=True)


class TestBuildSearchQueriesMei:
    def test_mei_queries_include_partner_name(self):
        queries = build_search_queries_mei(
            cnpj14="12345678000190",
            legal_name="JOAO DA SILVA 12345678000190",
            partner_names=["João da Silva"],
            city="São Paulo",
        )
        texts = [q.text for q in queries]
        assert any("João da Silva" in t for t in texts)

    def test_mei_queries_include_instagram_hint(self):
        queries = build_search_queries_mei(
            cnpj14="12345678000190",
            legal_name="MARIA SOUZA MEI",
            partner_names=["Maria Souza"],
            city="Campinas",
        )
        texts = [q.text for q in queries]
        assert any("instagram" in t.lower() or "whatsapp" in t.lower() for t in texts)

    def test_mei_always_returns_at_least_one_query(self):
        queries = build_search_queries_mei(
            cnpj14="12345678000190",
            legal_name=None,
            partner_names=[],
            city=None,
        )
        assert len(queries) >= 1

    def test_mei_queries_ordered_by_confidence_bonus_desc(self):
        queries = build_search_queries_mei(
            cnpj14="12345678000190",
            legal_name="JOAO SILVA MEI",
            partner_names=["João Silva"],
            city="Curitiba",
        )
        bonuses = [q.confidence_bonus for q in queries]
        assert bonuses == sorted(bonuses, reverse=True)

    def test_mei_cnpj_query_always_present(self):
        queries = build_search_queries_mei(
            cnpj14="12345678000190",
            legal_name=None,
            partner_names=["Pedro Alves"],
            city="Recife",
        )
        reasons = [q.reason for q in queries]
        assert "cnpj_exact" in reasons
        # Partner+instagram query must also be present
        assert any("mei_partner_instagram" in r for r in reasons)
