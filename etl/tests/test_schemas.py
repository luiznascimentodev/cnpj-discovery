import polars as pl
from schemas.base import TableSchema
from schemas import (
    EMPRESAS, ESTABELECIMENTOS, SOCIOS, SIMPLES,
    CNAES, MUNICIPIOS, FILE_PREFIX_MAP, MAIN_FILE_SCHEMAS,
)


class TestTableSchema:
    def test_polars_schema_all_utf8(self):
        schema = TableSchema(table="t", columns=["a", "b"], pk_columns=["a"], conflict_columns=["a"])
        assert schema.polars_schema == {"a": pl.Utf8, "b": pl.Utf8}

    def test_polars_schema_empty_columns(self):
        schema = TableSchema(table="t", columns=[], pk_columns=[], conflict_columns=[])
        assert schema.polars_schema == {}


class TestEmpresasSchema:
    def test_table_name(self):
        assert EMPRESAS.table == "empresas"

    def test_column_count(self):
        assert len(EMPRESAS.columns) == 7

    def test_first_column_is_cnpj_basico(self):
        assert EMPRESAS.columns[0] == "cnpj_basico"

    def test_pk_columns(self):
        assert EMPRESAS.pk_columns == ["cnpj_basico"]

    def test_conflict_columns(self):
        assert EMPRESAS.conflict_columns == ["cnpj_basico"]

    def test_polars_schema_has_all_columns(self):
        schema = EMPRESAS.polars_schema
        for col in EMPRESAS.columns:
            assert col in schema
            assert schema[col] == pl.Utf8


class TestEstabelecimentosSchema:
    def test_table_name(self):
        assert ESTABELECIMENTOS.table == "estabelecimentos"

    def test_column_count(self):
        assert len(ESTABELECIMENTOS.columns) == 30

    def test_pk_columns(self):
        assert ESTABELECIMENTOS.pk_columns == ["cnpj_basico", "cnpj_ordem", "cnpj_dv"]

    def test_email_column_present(self):
        assert "email" in ESTABELECIMENTOS.columns

    def test_cnae_principal_present(self):
        assert "cnae_principal" in ESTABELECIMENTOS.columns


class TestSociosSchema:
    def test_table_name(self):
        assert SOCIOS.table == "socios"

    def test_column_count(self):
        assert len(SOCIOS.columns) == 11

    def test_no_pk_columns(self):
        # socios usa BIGSERIAL — pk não vem do CSV
        assert SOCIOS.pk_columns == []


class TestSimplesSchema:
    def test_table_name(self):
        assert SIMPLES.table == "simples"

    def test_column_count(self):
        assert len(SIMPLES.columns) == 7

    def test_pk_is_cnpj_basico(self):
        assert SIMPLES.pk_columns == ["cnpj_basico"]


class TestDominiosSchema:
    def test_cnaes_table(self):
        assert CNAES.table == "cnaes"
        assert CNAES.columns == ["codigo", "descricao"]

    def test_municipios_table(self):
        assert MUNICIPIOS.table == "municipios"

    def test_file_prefix_map_keys(self):
        expected = {"CNAE", "Municipios", "Paises", "Naturezas", "Qualificacoes", "Motivos"}
        assert set(FILE_PREFIX_MAP.keys()) == expected

    def test_file_prefix_map_values_are_table_schemas(self):
        for schema in FILE_PREFIX_MAP.values():
            assert isinstance(schema, TableSchema)


class TestMainFileSchemas:
    def test_keys(self):
        expected = {"Empresas", "Estabelecimentos", "Socios", "Simples"}
        assert set(MAIN_FILE_SCHEMAS.keys()) == expected

    def test_values_are_table_schemas(self):
        for schema in MAIN_FILE_SCHEMAS.values():
            assert isinstance(schema, TableSchema)
