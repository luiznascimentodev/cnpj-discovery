from dataclasses import dataclass
import polars as pl


@dataclass
class TableSchema:
    table: str
    columns: list[str]
    pk_columns: list[str]           # colunas que formam a chave primária
    conflict_columns: list[str]     # colunas para ON CONFLICT DO UPDATE

    @property
    def polars_schema(self) -> dict[str, type]:
        """Polars schema: todas as colunas como Utf8 para leitura inicial"""
        return {col: pl.Utf8 for col in self.columns}
