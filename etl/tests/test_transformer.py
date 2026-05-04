"""Testes para etl/transformer.py — 100% de cobertura."""
from datetime import date
import polars as pl
import pytest

from transformer import (
    clean_cnpj_basico,
    parse_capital_social,
    parse_date_rf,
    transform_empresas,
    transform_estabelecimentos,
    transform_socios,
    transform_simples,
    transform_dominios,
    TRANSFORM_MAP,
)


# ─── Funções utilitárias ─────────────────────────────────────────────────────

class TestCleanCnpjBasico:
    def test_pads_short_cnpj(self):
        assert clean_cnpj_basico("1234567") == "01234567"

    def test_keeps_8_char_cnpj(self):
        assert clean_cnpj_basico("12345678") == "12345678"

    def test_strips_whitespace(self):
        assert clean_cnpj_basico("  1234  ") == "00001234"

    def test_all_zeros(self):
        assert clean_cnpj_basico("0") == "00000000"


class TestParseCapitalSocial:
    def test_normal_value(self):
        assert parse_capital_social("1234,56") == 1234.56

    def test_value_with_thousands_separator(self):
        assert parse_capital_social("1.234.567,89") == 1234567.89

    def test_empty_string(self):
        assert parse_capital_social("") is None

    def test_whitespace_only(self):
        assert parse_capital_social("   ") is None

    def test_invalid_string(self):
        assert parse_capital_social("N/A") is None

    def test_zero_value(self):
        assert parse_capital_social("0,00") == 0.0

    def test_strips_whitespace(self):
        assert parse_capital_social("  100,00  ") == 100.0


class TestParseDateRf:
    def test_valid_date(self):
        assert parse_date_rf("20230115") == date(2023, 1, 15)

    def test_zeroed_date_returns_none(self):
        assert parse_date_rf("00000000") is None

    def test_empty_string_returns_none(self):
        assert parse_date_rf("") is None

    def test_invalid_date_returns_none(self):
        assert parse_date_rf("99999999") is None

    def test_strips_whitespace(self):
        assert parse_date_rf("  20230101  ") == date(2023, 1, 1)

    def test_invalid_month_returns_none(self):
        assert parse_date_rf("20231399") is None


# ─── transform_empresas ──────────────────────────────────────────────────────

class TestTransformEmpresas:
    def _make_df(self, rows: list[dict]) -> pl.DataFrame:
        from schemas import EMPRESAS
        return pl.DataFrame(rows, schema={c: pl.Utf8 for c in EMPRESAS.columns})

    def test_pads_cnpj_basico(self):
        df = self._make_df([{
            "cnpj_basico": "1234567", "razao_social": "EMPRESA A",
            "natureza_juridica": "2062", "qualificacao_resp": "49",
            "capital_social": "1000,00", "porte": "3", "ente_federativo": "",
        }])
        result = transform_empresas(df)
        assert result["cnpj_basico"][0] == "01234567"

    def test_converts_capital_social(self):
        df = self._make_df([{
            "cnpj_basico": "00000001", "razao_social": "EMPRESA B",
            "natureza_juridica": "2062", "qualificacao_resp": "49",
            "capital_social": "1.234.567,89", "porte": "5", "ente_federativo": "",
        }])
        result = transform_empresas(df)
        assert result["capital_social"][0] == pytest.approx(1234567.89)

    def test_invalid_capital_social_becomes_null(self):
        df = self._make_df([{
            "cnpj_basico": "00000001", "razao_social": "X",
            "natureza_juridica": "", "qualificacao_resp": "",
            "capital_social": "N/A", "porte": "", "ente_federativo": "",
        }])
        result = transform_empresas(df)
        assert result["capital_social"][0] is None

    def test_porte_cast_to_int16(self):
        df = self._make_df([{
            "cnpj_basico": "00000001", "razao_social": "X",
            "natureza_juridica": "2062", "qualificacao_resp": "49",
            "capital_social": "100,00", "porte": "1", "ente_federativo": "",
        }])
        result = transform_empresas(df)
        assert result["porte"].dtype == pl.Int16
        assert result["porte"][0] == 1

    def test_strips_whitespace_from_razao_social(self):
        df = self._make_df([{
            "cnpj_basico": "00000001", "razao_social": "  EMPRESA C  ",
            "natureza_juridica": "", "qualificacao_resp": "",
            "capital_social": "", "porte": "", "ente_federativo": "",
        }])
        result = transform_empresas(df)
        assert result["razao_social"][0] == "EMPRESA C"


# ─── transform_estabelecimentos ─────────────────────────────────────────────

class TestTransformEstabelecimentos:
    def _make_row(self, overrides: dict = {}) -> dict:
        from schemas import ESTABELECIMENTOS
        row = {c: "" for c in ESTABELECIMENTOS.columns}
        row.update({
            "cnpj_basico": "00000001", "cnpj_ordem": "0001", "cnpj_dv": "00",
            "data_situacao": "20230101", "data_inicio": "20100615", "data_situacao_esp": "00000000",
        })
        row.update(overrides)
        return row

    def _make_df(self, rows: list[dict]) -> pl.DataFrame:
        from schemas import ESTABELECIMENTOS
        return pl.DataFrame(rows, schema={c: pl.Utf8 for c in ESTABELECIMENTOS.columns})

    def test_parses_data_inicio(self):
        df = self._make_df([self._make_row()])
        result = transform_estabelecimentos(df)
        assert result["data_inicio"][0] == date(2010, 6, 15)

    def test_zeroed_date_becomes_null(self):
        df = self._make_df([self._make_row()])
        result = transform_estabelecimentos(df)
        assert result["data_situacao_esp"][0] is None

    def test_email_lowercased(self):
        df = self._make_df([self._make_row({"email": "CONTATO@EMPRESA.COM"})])
        result = transform_estabelecimentos(df)
        assert result["email"][0] == "contato@empresa.com"

    def test_cep_removes_non_numeric(self):
        df = self._make_df([self._make_row({"cep": "01310-100"})])
        result = transform_estabelecimentos(df)
        assert result["cep"][0] == "01310100"

    def test_cnae_principal_cast_to_int32(self):
        df = self._make_df([self._make_row({"cnae_principal": "6201500"})])
        result = transform_estabelecimentos(df)
        assert result["cnae_principal"].dtype == pl.Int32
        assert result["cnae_principal"][0] == 6201500

    def test_situacao_cadastral_cast_to_int16(self):
        df = self._make_df([self._make_row({"situacao_cadastral": "2"})])
        result = transform_estabelecimentos(df)
        assert result["situacao_cadastral"].dtype == pl.Int16
        assert result["situacao_cadastral"][0] == 2


# ─── transform_socios ────────────────────────────────────────────────────────

class TestTransformSocios:
    def _make_df(self, rows: list[dict]) -> pl.DataFrame:
        from schemas import SOCIOS
        return pl.DataFrame(rows, schema={c: pl.Utf8 for c in SOCIOS.columns})

    def test_parses_data_entrada(self):
        df = self._make_df([{
            "cnpj_basico": "00000001", "identificador": "1",
            "nome_socio": "JOAO SILVA", "cpf_cnpj_socio": "***.***.***-**",
            "qualificacao": "49", "data_entrada": "20200101",
            "pais": "", "repr_legal": "", "nome_repr": "",
            "qualificacao_repr": "", "faixa_etaria": "4",
        }])
        result = transform_socios(df)
        assert result["data_entrada"][0] == date(2020, 1, 1)

    def test_zeroed_data_entrada_becomes_null(self):
        df = self._make_df([{
            "cnpj_basico": "00000001", "identificador": "1",
            "nome_socio": "MARIA", "cpf_cnpj_socio": "",
            "qualificacao": "49", "data_entrada": "00000000",
            "pais": "", "repr_legal": "", "nome_repr": "",
            "qualificacao_repr": "", "faixa_etaria": "",
        }])
        result = transform_socios(df)
        assert result["data_entrada"][0] is None


# ─── transform_simples ───────────────────────────────────────────────────────

class TestTransformSimples:
    def _make_df(self, rows: list[dict]) -> pl.DataFrame:
        from schemas import SIMPLES
        return pl.DataFrame(rows, schema={c: pl.Utf8 for c in SIMPLES.columns})

    def test_parses_dates(self):
        df = self._make_df([{
            "cnpj_basico": "00000001", "opcao_simples": "S",
            "data_opcao_simples": "20180101", "data_exc_simples": "00000000",
            "opcao_mei": "N", "data_opcao_mei": "00000000", "data_exc_mei": "00000000",
        }])
        result = transform_simples(df)
        assert result["data_opcao_simples"][0] == date(2018, 1, 1)
        assert result["data_exc_simples"][0] is None


# ─── transform_dominios ──────────────────────────────────────────────────────

class TestTransformDominios:
    def test_cast_codigo_to_int32(self):
        df = pl.DataFrame(
            [{"codigo": "  6201500  ", "descricao": " Desenvolvimento de programas de computador "}],
            schema={"codigo": pl.Utf8, "descricao": pl.Utf8},
        )
        result = transform_dominios(df)
        assert result["codigo"].dtype == pl.Int32
        assert result["codigo"][0] == 6201500
        assert result["descricao"][0] == "Desenvolvimento de programas de computador"

    def test_invalid_codigo_becomes_null(self):
        df = pl.DataFrame(
            [{"codigo": "ABC", "descricao": "INVALIDO"}],
            schema={"codigo": pl.Utf8, "descricao": pl.Utf8},
        )
        result = transform_dominios(df)
        assert result["codigo"][0] is None


# ─── TRANSFORM_MAP ────────────────────────────────────────────────────────────

class TestTransformMap:
    def test_all_main_tables_present(self):
        expected = {"empresas", "estabelecimentos", "socios", "simples"}
        assert expected.issubset(set(TRANSFORM_MAP.keys()))

    def test_all_domain_tables_present(self):
        expected = {"cnaes", "municipios", "paises", "naturezas", "qualificacoes", "motivos"}
        assert expected.issubset(set(TRANSFORM_MAP.keys()))

    def test_all_values_are_callable(self):
        for fn in TRANSFORM_MAP.values():
            assert callable(fn)
