"""Tests for models/filters.py, models/empresa.py, and services/query_builder.py."""
from datetime import date

import pytest
from pydantic import ValidationError

from models.empresa import EmpresaOut
from models.filters import ProspectingFilters
from services.query_builder import build_prospecting_query


# ---------------------------------------------------------------------------
# ProspectingFilters
# ---------------------------------------------------------------------------


class TestProspectingFilters:
    def test_defaults(self):
        f = ProspectingFilters()
        assert f.situacao_cadastral == 2
        assert f.limit == 50
        assert f.excluir_mei is False
        assert f.uf is None
        assert f.municipio is None
        assert f.cnae_principal is None
        assert f.porte is None
        assert f.capital_social_min is None
        assert f.capital_social_max is None
        assert f.busca_razao is None
        assert f.cursor_cnpj_basico is None
        assert f.cursor_cnpj_ordem is None

    def test_limit_min(self):
        f = ProspectingFilters(limit=1)
        assert f.limit == 1

    def test_limit_max(self):
        f = ProspectingFilters(limit=500)
        assert f.limit == 500

    def test_limit_below_min_raises(self):
        with pytest.raises(ValidationError):
            ProspectingFilters(limit=0)

    def test_limit_above_max_raises(self):
        with pytest.raises(ValidationError):
            ProspectingFilters(limit=501)

    def test_busca_razao_min_length(self):
        f = ProspectingFilters(busca_razao="ab")
        assert f.busca_razao == "ab"

    def test_busca_razao_too_short_raises(self):
        with pytest.raises(ValidationError):
            ProspectingFilters(busca_razao="a")

    def test_uf_max_length(self):
        f = ProspectingFilters(uf="SP")
        assert f.uf == "SP"

    def test_uf_too_long_raises(self):
        with pytest.raises(ValidationError):
            ProspectingFilters(uf="SPX")

    def test_capital_social_min_zero(self):
        f = ProspectingFilters(capital_social_min=0)
        assert f.capital_social_min == 0.0

    def test_capital_social_min_negative_raises(self):
        with pytest.raises(ValidationError):
            ProspectingFilters(capital_social_min=-1)

    def test_capital_social_max_zero(self):
        f = ProspectingFilters(capital_social_max=0)
        assert f.capital_social_max == 0.0

    def test_capital_social_max_negative_raises(self):
        with pytest.raises(ValidationError):
            ProspectingFilters(capital_social_max=-0.01)

    def test_excluir_mei_true(self):
        f = ProspectingFilters(excluir_mei=True)
        assert f.excluir_mei is True

    def test_porte_mei_with_excluir_mei_raises(self):
        with pytest.raises(ValidationError, match="mutuamente exclusivos"):
            ProspectingFilters(porte=1, excluir_mei=True)

    def test_porte_non_mei_with_excluir_mei_ok(self):
        f = ProspectingFilters(porte=2, excluir_mei=True)
        assert f.porte == 2
        assert f.excluir_mei is True

    def test_situacao_cadastral_none(self):
        f = ProspectingFilters(situacao_cadastral=None)
        assert f.situacao_cadastral is None


# ---------------------------------------------------------------------------
# EmpresaOut
# ---------------------------------------------------------------------------


class TestEmpresaOut:
    def _required_fields(self):
        return dict(
            cnpj_basico="12345678",
            cnpj_ordem="0001",
            cnpj_dv="90",
            cnpj_completo="12345678000190",
            razao_social="EMPRESA TESTE LTDA",
        )

    def test_required_fields_only(self):
        e = EmpresaOut(**self._required_fields())
        assert e.cnpj_basico == "12345678"
        assert e.cnpj_ordem == "0001"
        assert e.cnpj_dv == "90"
        assert e.cnpj_completo == "12345678000190"
        assert e.razao_social == "EMPRESA TESTE LTDA"

    def test_optional_fields_default_to_none(self):
        e = EmpresaOut(**self._required_fields())
        assert e.nome_fantasia is None
        assert e.situacao_cadastral is None
        assert e.cnae_principal is None
        assert e.cnae_descricao is None
        assert e.uf is None
        assert e.municipio is None
        assert e.municipio_descricao is None
        assert e.email is None
        assert e.telefone1 is None
        assert e.porte is None
        assert e.capital_social is None
        assert e.data_inicio is None

    def test_date_field_accepts_date_object(self):
        d = date(2020, 1, 15)
        e = EmpresaOut(**self._required_fields(), data_inicio=d)
        assert e.data_inicio == d

    def test_all_optional_fields(self):
        e = EmpresaOut(
            **self._required_fields(),
            nome_fantasia="FANTASIA",
            situacao_cadastral=2,
            cnae_principal=6201500,
            cnae_descricao="Desenvolvimento de programas",
            uf="SP",
            municipio=3550308,
            municipio_descricao="São Paulo",
            email="contato@empresa.com",
            telefone1="1133334444",
            porte=3,
            capital_social=100000.0,
            data_inicio=date(2010, 5, 20),
        )
        assert e.nome_fantasia == "FANTASIA"
        assert e.situacao_cadastral == 2
        assert e.cnae_principal == 6201500
        assert e.cnae_descricao == "Desenvolvimento de programas"
        assert e.uf == "SP"
        assert e.municipio == 3550308
        assert e.municipio_descricao == "São Paulo"
        assert e.email == "contato@empresa.com"
        assert e.telefone1 == "1133334444"
        assert e.porte == 3
        assert e.capital_social == 100000.0
        assert e.data_inicio == date(2010, 5, 20)

    def test_missing_required_field_raises(self):
        data = self._required_fields()
        del data["razao_social"]
        with pytest.raises(ValidationError):
            EmpresaOut(**data)


# ---------------------------------------------------------------------------
# build_prospecting_query
# ---------------------------------------------------------------------------


class TestBuildProspectingQueryNoFilters:
    def test_no_conditions_no_where_clause(self):
        f = ProspectingFilters(situacao_cadastral=None)
        sql, params = build_prospecting_query(f)
        assert "WHERE" not in sql
        assert params == []

    def test_default_limit_50(self):
        f = ProspectingFilters(situacao_cadastral=None)
        sql, params = build_prospecting_query(f)
        assert sql.strip().endswith("LIMIT 50")

    def test_always_has_order_by(self):
        f = ProspectingFilters(situacao_cadastral=None)
        sql, _ = build_prospecting_query(f)
        assert "ORDER BY est.cnpj_basico, est.cnpj_ordem" in sql

    def test_returns_tuple_of_sql_and_list(self):
        f = ProspectingFilters(situacao_cadastral=None)
        result = build_prospecting_query(f)
        assert isinstance(result, tuple)
        sql, params = result
        assert isinstance(sql, str)
        assert isinstance(params, list)


class TestBuildProspectingQuerySituacaoCadastral:
    def test_adds_condition(self):
        f = ProspectingFilters(situacao_cadastral=2)
        sql, params = build_prospecting_query(f)
        assert "est.situacao_cadastral = $1" in sql
        assert params[0] == 2

    def test_situacao_cadastral_none_not_added(self):
        f = ProspectingFilters(situacao_cadastral=None)
        sql, params = build_prospecting_query(f)
        # No WHERE clause should be generated when situacao_cadastral is None
        assert "WHERE" not in sql
        assert "situacao_cadastral = $" not in sql
        assert params == []


class TestBuildProspectingQueryUf:
    def test_adds_uf_condition_uppercased(self):
        f = ProspectingFilters(situacao_cadastral=None, uf="sp")
        sql, params = build_prospecting_query(f)
        assert "est.uf = $1" in sql
        assert params[0] == "SP"

    def test_uf_already_uppercase(self):
        f = ProspectingFilters(situacao_cadastral=None, uf="RJ")
        _, params = build_prospecting_query(f)
        assert params[0] == "RJ"


class TestBuildProspectingQueryMunicipio:
    def test_adds_municipio_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, municipio=3550308)
        sql, params = build_prospecting_query(f)
        assert "est.municipio = $1" in sql
        assert params[0] == 3550308


class TestBuildProspectingQueryCnaePrincipal:
    def test_adds_cnae_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, cnae_principal=6201500)
        sql, params = build_prospecting_query(f)
        assert "est.cnae_principal = $1" in sql
        assert params[0] == 6201500


class TestBuildProspectingQueryPorte:
    def test_adds_porte_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, porte=3)
        sql, params = build_prospecting_query(f)
        assert "e.porte = $1" in sql
        assert params[0] == 3


class TestBuildProspectingQueryExcluirMei:
    def test_excluir_mei_adds_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, excluir_mei=True)
        sql, params = build_prospecting_query(f)
        assert "(e.porte IS NULL OR e.porte != 1)" in sql
        # excluir_mei doesn't add a param
        assert params == []

    def test_excluir_mei_false_no_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, excluir_mei=False)
        sql, params = build_prospecting_query(f)
        assert "e.porte IS NULL" not in sql


class TestBuildProspectingQueryCapitalSocial:
    def test_capital_social_min_adds_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, capital_social_min=10000.0)
        sql, params = build_prospecting_query(f)
        assert "e.capital_social >= $1" in sql
        assert params[0] == 10000.0

    def test_capital_social_max_adds_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, capital_social_max=500000.0)
        sql, params = build_prospecting_query(f)
        assert "e.capital_social <= $1" in sql
        assert params[0] == 500000.0

    def test_capital_social_min_and_max(self):
        f = ProspectingFilters(
            situacao_cadastral=None,
            capital_social_min=1000.0,
            capital_social_max=9000.0,
        )
        sql, params = build_prospecting_query(f)
        assert "e.capital_social >= $1" in sql
        assert "e.capital_social <= $2" in sql
        assert params == [1000.0, 9000.0]


class TestBuildProspectingQueryBuscaRazao:
    def test_adds_fulltext_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, busca_razao="tecnologia")
        sql, params = build_prospecting_query(f)
        assert "to_tsvector" in sql
        assert "plainto_tsquery" in sql
        assert params[0] == "tecnologia"

    def test_same_param_index_used_twice(self):
        """busca_razao uses $p for both razao_social and nome_fantasia."""
        f = ProspectingFilters(situacao_cadastral=None, busca_razao="software")
        sql, params = build_prospecting_query(f)
        # param index $1 should appear twice in the condition (once for each tsvector)
        assert sql.count("$1") == 2
        # only one param appended
        assert len(params) == 1

    def test_busca_razao_after_situacao_uses_correct_index(self):
        f = ProspectingFilters(situacao_cadastral=2, busca_razao="logistica")
        sql, params = build_prospecting_query(f)
        # situacao_cadastral takes $1, busca_razao takes $2 (used twice)
        assert "est.situacao_cadastral = $1" in sql
        assert sql.count("$2") == 2
        assert params == [2, "logistica"]


class TestBuildProspectingQueryCursor:
    def test_cursor_both_fields_adds_keyset(self):
        f = ProspectingFilters(
            situacao_cadastral=None,
            cursor_cnpj_basico="12345678",
            cursor_cnpj_ordem="0001",
        )
        sql, params = build_prospecting_query(f)
        assert "(est.cnpj_basico, est.cnpj_ordem) > ($1, $2)" in sql
        assert params == ["12345678", "0001"]

    def test_cursor_only_basico_no_keyset(self):
        f = ProspectingFilters(
            situacao_cadastral=None,
            cursor_cnpj_basico="12345678",
            cursor_cnpj_ordem=None,
        )
        sql, params = build_prospecting_query(f)
        assert "est.cnpj_basico, est.cnpj_ordem) >" not in sql
        assert params == []

    def test_cursor_only_ordem_no_keyset(self):
        f = ProspectingFilters(
            situacao_cadastral=None,
            cursor_cnpj_basico=None,
            cursor_cnpj_ordem="0001",
        )
        sql, params = build_prospecting_query(f)
        assert "(est.cnpj_basico, est.cnpj_ordem) >" not in sql
        assert params == []

    def test_cursor_after_filters_uses_correct_indices(self):
        f = ProspectingFilters(
            situacao_cadastral=2,
            uf="SP",
            cursor_cnpj_basico="99999999",
            cursor_cnpj_ordem="0002",
        )
        sql, params = build_prospecting_query(f)
        # situacao_cadastral=$1, uf=$2, cursor=$3/$4
        assert "est.situacao_cadastral = $1" in sql
        assert "est.uf = $2" in sql
        assert "(est.cnpj_basico, est.cnpj_ordem) > ($3, $4)" in sql
        assert params == [2, "SP", "99999999", "0002"]


class TestBuildProspectingQueryMultipleFilters:
    def test_all_filters_combined_param_count(self):
        f = ProspectingFilters(
            situacao_cadastral=2,
            uf="MG",
            municipio=3106200,
            cnae_principal=4711302,
            porte=3,
            excluir_mei=True,
            capital_social_min=5000.0,
            capital_social_max=1000000.0,
            busca_razao="mercearia",
            cursor_cnpj_basico="11111111",
            cursor_cnpj_ordem="0001",
            limit=100,
        )
        sql, params = build_prospecting_query(f)
        # situacao=1, uf=2, municipio=3, cnae=4, porte=5,
        # excluir_mei adds no param, capital_min=6, capital_max=7, busca=8, cursor=9,10
        assert len(params) == 10
        assert params[0] == 2          # situacao_cadastral
        assert params[1] == "MG"       # uf (uppercased)
        assert params[2] == 3106200    # municipio
        assert params[3] == 4711302    # cnae_principal
        assert params[4] == 3          # porte
        assert params[5] == 5000.0     # capital_social_min
        assert params[6] == 1000000.0  # capital_social_max
        assert params[7] == "mercearia"  # busca_razao
        assert params[8] == "11111111"   # cursor_basico
        assert params[9] == "0001"       # cursor_ordem

    def test_all_filters_sql_has_where(self):
        f = ProspectingFilters(situacao_cadastral=2, uf="SP")
        sql, _ = build_prospecting_query(f)
        assert "WHERE" in sql

    def test_limit_respected_in_sql(self):
        f = ProspectingFilters(situacao_cadastral=None, limit=200)
        sql, _ = build_prospecting_query(f)
        assert sql.strip().endswith("LIMIT 200")

    def test_order_by_always_before_limit(self):
        f = ProspectingFilters(situacao_cadastral=2, uf="RJ", limit=10)
        sql, _ = build_prospecting_query(f)
        order_pos = sql.index("ORDER BY")
        limit_pos = sql.index("LIMIT")
        assert order_pos < limit_pos

    def test_conditions_joined_with_and(self):
        f = ProspectingFilters(situacao_cadastral=2, uf="SP", municipio=3550308)
        sql, _ = build_prospecting_query(f)
        assert " AND " in sql
