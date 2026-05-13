"""Tests for models/filters.py, models/empresa.py, models/detail.py, and services/query_builder.py."""
from datetime import date

import pytest
from pydantic import ValidationError

from models.detail import CnaeItem, EmpresaDetail, SimplesOut, SocioOut
from models.empresa import EmpresaOut
from models.filters import ProspectingFilters
from services.query_builder import build_enrichment_candidate_query, build_prospecting_query


# ---------------------------------------------------------------------------
# ProspectingFilters
# ---------------------------------------------------------------------------


class TestProspectingFilters:
    def test_defaults(self):
        f = ProspectingFilters()
        assert f.situacao_cadastral == 2
        assert f.limit == 100
        assert f.excluir_mei is False
        assert f.uf is None
        assert f.municipio is None
        assert f.cnaes is None
        assert f.porte is None
        assert f.capital_social_min is None
        assert f.capital_social_max is None
        assert f.cursor_cnpj_basico is None
        assert f.cursor_cnpj_ordem is None

    def test_limit_min(self):
        f = ProspectingFilters(limit=50)
        assert f.limit == 50

    def test_limit_max(self):
        f = ProspectingFilters(limit=50_000)
        assert f.limit == 50_000

    def test_limit_below_min_raises(self):
        with pytest.raises(ValidationError):
            ProspectingFilters(limit=49)

    def test_limit_above_max_raises(self):
        with pytest.raises(ValidationError):
            ProspectingFilters(limit=50_001)

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
            ProspectingFilters(porte=[1], excluir_mei=True)

    def test_porte_non_mei_with_excluir_mei_ok(self):
        f = ProspectingFilters(porte=[2], excluir_mei=True)
        assert f.porte == [2]
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

    def test_default_limit_100(self):
        f = ProspectingFilters(situacao_cadastral=None)
        sql, params = build_prospecting_query(f)
        assert "LIMIT 100" in sql

    def test_always_has_order_by(self):
        f = ProspectingFilters(situacao_cadastral=None)
        sql, _ = build_prospecting_query(f)
        assert "ORDER BY est.cnpj_basico, est.cnpj_ordem" in sql
        assert "WITH candidate_est AS MATERIALIZED" in sql

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


class TestBuildProspectingQueryCnaes:
    def test_single_cnae_uses_any(self):
        f = ProspectingFilters(situacao_cadastral=None, cnaes=[6201500])
        sql, params = build_prospecting_query(f)
        assert "est.cnae_principal = ANY($1::int[])" in sql
        assert params[0] == [6201500]

    def test_multiple_cnaes(self):
        f = ProspectingFilters(situacao_cadastral=None, cnaes=[6201500, 6209100])
        sql, params = build_prospecting_query(f)
        assert "est.cnae_principal = ANY($1::int[])" in sql
        assert params[0] == [6201500, 6209100]

    def test_cnaes_none_no_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, cnaes=None)
        sql, params = build_prospecting_query(f)
        assert "est.cnae_principal = ANY" not in sql
        assert params == []


class TestBuildProspectingQueryPorte:
    def test_adds_porte_any_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, porte=[3])
        sql, params = build_prospecting_query(f)
        assert "e.porte = ANY($1::int[])" in sql
        assert params[0] == [3]

    def test_multiple_portes(self):
        f = ProspectingFilters(situacao_cadastral=None, porte=[2, 3])
        sql, params = build_prospecting_query(f)
        assert "e.porte = ANY($1::int[])" in sql
        assert params[0] == [2, 3]


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
            cnaes=[4711302],
            porte=[3],
            excluir_mei=True,
            capital_social_min=5000.0,
            capital_social_max=1000000.0,
            cursor_cnpj_basico="11111111",
            cursor_cnpj_ordem="0001",
            limit=100,
        )
        sql, params = build_prospecting_query(f)
        # situacao=1, uf=2, municipio=3, cnaes=4, porte=5,
        # excluir_mei adds no param, capital_min=6, capital_max=7, cursor=8,9
        assert len(params) == 9
        assert params[0] == 2            # situacao_cadastral
        assert params[1] == "MG"         # uf (uppercased)
        assert params[2] == 3106200      # municipio
        assert params[3] == [4711302]    # cnaes
        assert params[4] == [3]          # porte
        assert params[5] == 5000.0       # capital_social_min
        assert params[6] == 1000000.0    # capital_social_max
        assert params[7] == "11111111"   # cursor_basico
        assert params[8] == "0001"       # cursor_ordem

    def test_all_filters_sql_has_where(self):
        f = ProspectingFilters(situacao_cadastral=2, uf="SP")
        sql, _ = build_prospecting_query(f)
        assert "WHERE" in sql

    def test_limit_respected_in_sql(self):
        f = ProspectingFilters(situacao_cadastral=None, limit=50)
        sql, _ = build_prospecting_query(f)
        assert "LIMIT 50" in sql

    def test_order_by_always_before_limit(self):
        f = ProspectingFilters(situacao_cadastral=2, uf="RJ", limit=50)
        sql, _ = build_prospecting_query(f)
        order_pos = sql.index("ORDER BY")
        limit_pos = sql.index("LIMIT")
        assert order_pos < limit_pos

    def test_include_limit_false_omits_limit_and_cursor(self):
        f = ProspectingFilters(
            situacao_cadastral=2,
            cursor_cnpj_basico="12345678",
            cursor_cnpj_ordem="0001",
            limit=50,
        )
        sql, params = build_prospecting_query(f, include_limit=False)
        assert "LIMIT" not in sql
        assert "(est.cnpj_basico, est.cnpj_ordem) >" not in sql
        assert params == [2]

    def test_conditions_joined_with_and(self):
        f = ProspectingFilters(situacao_cadastral=2, uf="SP", municipio=3550308)
        sql, _ = build_prospecting_query(f)
        assert " AND " in sql


# ---------------------------------------------------------------------------
# Detail models
# ---------------------------------------------------------------------------


class TestDetailModels:
    def _empresa_required(self):
        return dict(
            cnpj_basico="12345678", cnpj_ordem="0001", cnpj_dv="90",
            cnpj_completo="12345678000190", razao_social="TESTE LTDA",
        )

    def test_empresa_detail_required_fields(self):
        e = EmpresaDetail(**self._empresa_required())
        assert e.cnpj_completo == "12345678000190"
        assert e.cnae_secundarios == []
        assert e.socios == []
        assert e.simples is None

    def test_empresa_detail_with_nested(self):
        e = EmpresaDetail(
            **self._empresa_required(),
            cnae_secundarios=[CnaeItem(codigo=6201500, descricao="Dev")],
            socios=[SocioOut(nome_socio="JOAO", qualificacao=49)],
            simples=SimplesOut(opcao_simples="S"),
        )
        assert e.cnae_secundarios[0].codigo == 6201500
        assert e.socios[0].nome_socio == "JOAO"
        assert e.simples.opcao_simples == "S"

    def test_cnae_item_descricao_optional(self):
        c = CnaeItem(codigo=6201500)
        assert c.descricao is None

    def test_socio_all_optional(self):
        s = SocioOut()
        assert s.nome_socio is None
        assert s.data_entrada is None

    def test_simples_all_optional(self):
        s = SimplesOut()
        assert s.opcao_simples is None
        assert s.opcao_mei is None


# ---------------------------------------------------------------------------
# New filter validators
# ---------------------------------------------------------------------------


class TestProspectingFiltersCnpj:
    def test_cnpj_strips_punctuation(self):
        f = ProspectingFilters(cnpj="12.345.678/0001-90")
        assert f.cnpj == "12345678000190"

    def test_cnpj_without_punctuation_accepted(self):
        f = ProspectingFilters(cnpj="12345678000190")
        assert f.cnpj == "12345678000190"

    def test_cnpj_wrong_length_raises(self):
        with pytest.raises(ValidationError, match="14 dígitos"):
            ProspectingFilters(cnpj="123456")

    def test_cnpj_none_accepted(self):
        f = ProspectingFilters()
        assert f.cnpj is None


class TestProspectingFiltersDateRange:
    def test_valid_date_range(self):
        f = ProspectingFilters(
            data_inicio_min=date(2020, 1, 1),
            data_inicio_max=date(2023, 12, 31),
        )
        assert f.data_inicio_min == date(2020, 1, 1)

    def test_inverted_date_range_raises(self):
        with pytest.raises(ValidationError, match="data_inicio_min"):
            ProspectingFilters(
                data_inicio_min=date(2024, 1, 1),
                data_inicio_max=date(2020, 1, 1),
            )

    def test_only_min_accepted(self):
        f = ProspectingFilters(data_inicio_min=date(2020, 1, 1))
        assert f.data_inicio_max is None


# ---------------------------------------------------------------------------
# New query builder filter paths
# ---------------------------------------------------------------------------


class TestBuildProspectingQueryCnpjMode:
    def test_cnpj_mode_splits_into_pk(self):
        f = ProspectingFilters(cnpj="12345678000190", situacao_cadastral=2, uf="SP")
        sql, params = build_prospecting_query(f)
        assert params == ["12345678", "0001", "90"]
        assert "LIMIT 1" in sql

    def test_cnpj_mode_ignores_other_filters(self):
        f = ProspectingFilters(cnpj="12345678000190", situacao_cadastral=2, uf="SP")
        sql, params = build_prospecting_query(f)
        assert "est.uf =" not in sql
        assert "situacao_cadastral =" not in sql


class TestBuildEnrichmentCandidateQuery:
    def test_wraps_bounded_prospecting_query(self):
        filters = ProspectingFilters(uf="SP", limit=100)
        sql, params = build_enrichment_candidate_query(filters, max_items=500)

        assert "enrichment_candidates" in sql
        assert "LIMIT 500" in sql
        assert params == [2, "SP"]

    def test_requires_positive_max_items(self):
        with pytest.raises(ValueError):
            build_enrichment_candidate_query(ProspectingFilters(), max_items=0)


class TestBuildProspectingQueryNewFilters:
    def test_bairro_uses_canonical_exact_match(self):
        f = ProspectingFilters(situacao_cadastral=None, bairro="centro")
        sql, params = build_prospecting_query(f)
        assert "upper(est.bairro)" in sql
        assert "= $1" in sql
        assert params[0] == "CENTRO"

    def test_matriz_filial_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, matriz_filial=1)
        sql, params = build_prospecting_query(f)
        assert "est.matriz_filial = $1" in sql
        assert params[0] == 1

    def test_data_inicio_min_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, data_inicio_min=date(2020, 1, 1))
        sql, params = build_prospecting_query(f)
        assert "est.data_inicio >= $1" in sql
        assert params[0] == date(2020, 1, 1)

    def test_data_inicio_max_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, data_inicio_max=date(2023, 12, 31))
        sql, params = build_prospecting_query(f)
        assert "est.data_inicio <= $1" in sql
        assert params[0] == date(2023, 12, 31)

    def test_natureza_juridica_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, natureza_juridica=2062)
        sql, params = build_prospecting_query(f)
        assert "e.natureza_juridica = $1" in sql
        assert params[0] == 2062

    def test_opcao_simples_true_adds_join_and_condition(self):
        f = ProspectingFilters(situacao_cadastral=None, opcao_simples=True)
        sql, params = build_prospecting_query(f)
        assert "JOIN simples" in sql
        assert "s.opcao_simples = $1" in sql
        assert params[0] == "S"

    def test_opcao_simples_false_filters_non_simples(self):
        f = ProspectingFilters(situacao_cadastral=None, opcao_simples=False)
        sql, params = build_prospecting_query(f)
        assert "JOIN simples" in sql
        assert params[0] == "N"

    def test_opcao_simples_none_no_join(self):
        f = ProspectingFilters(situacao_cadastral=None, opcao_simples=None)
        sql, params = build_prospecting_query(f)
        assert "JOIN simples" not in sql

    def test_limit_50000_accepted(self):
        f = ProspectingFilters(limit=50_000)
        assert f.limit == 50_000

    def test_limit_50001_raises(self):
        with pytest.raises(ValidationError):
            ProspectingFilters(limit=50_001)
