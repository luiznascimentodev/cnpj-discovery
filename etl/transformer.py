"""
Transformer ETL — limpeza e normalização de dados da Receita Federal.

Todas as funções operam sobre pl.DataFrame inteiro (vetorizado via Polars)
para máxima performance. Os dados entram como Utf8 puro do CSV e saem
com tipos corretos prontos para inserção no PostgreSQL.
"""
from datetime import date
from typing import Optional

import polars as pl
from loguru import logger


# ─── Funções utilitárias (usadas nos testes unitários e pelo transformer DF) ──

def clean_cnpj_basico(value: str) -> str:
    """Padeia CNPJ basico com zeros à esquerda até 8 chars."""
    return value.strip().zfill(8)


def parse_capital_social(value: str) -> Optional[float]:
    """
    Converte capital social formato BR (1.234,56) para float.
    Retorna None para valores vazios ou inválidos.
    """
    v = value.strip() if value else ""
    if not v:
        return None
    try:
        return float(v.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def parse_date_rf(value: str) -> Optional[date]:
    """
    Converte data no formato YYYYMMDD para date.
    Retorna None para '00000000' ou strings inválidas.
    """
    v = value.strip() if value else ""
    if not v or v == "00000000":
        return None
    try:
        return date(int(v[:4]), int(v[4:6]), int(v[6:8]))
    except (ValueError, IndexError):
        return None


# ─── Funções de transformação de DataFrame (Polars vetorizado) ───────────────

def transform_empresas(df: pl.DataFrame) -> pl.DataFrame:
    """
    Normaliza DataFrame de empresas:
    - cnpj_basico: strip + zfill(8)
    - razao_social: strip
    - natureza_juridica, qualificacao_resp, porte: strip → Int16 (None se inválido)
    - capital_social: strip, substituir ponto por '', vírgula por '.' → Float64
    - ente_federativo: strip (pode ser nulo)
    """
    return df.with_columns([
        pl.col("cnpj_basico").str.strip_chars().str.zfill(8),
        pl.col("razao_social").str.strip_chars(),
        pl.col("natureza_juridica").str.strip_chars().cast(pl.Int16, strict=False),
        pl.col("qualificacao_resp").str.strip_chars().cast(pl.Int16, strict=False),
        pl.col("capital_social")
            .str.strip_chars()
            .str.replace_all(r"\.", "", literal=False)
            .str.replace(",", ".", literal=True)
            .cast(pl.Float64, strict=False),
        pl.col("porte").str.strip_chars().cast(pl.Int16, strict=False),
        pl.col("ente_federativo").str.strip_chars(),
    ])


def transform_estabelecimentos(df: pl.DataFrame) -> pl.DataFrame:
    """
    Normaliza DataFrame de estabelecimentos:
    - cnpj_basico: strip + zfill(8)
    - cnpj_ordem, cnpj_dv: strip
    - campos Int16: matriz_filial, situacao_cadastral, motivo_situacao, pais, municipio
    - cnae_principal: Int32 (código CNAE pode ser > 32k)
    - cep: strip + remove não-numéricos
    - email: strip + lowercase
    - datas (data_situacao, data_inicio, data_situacao_esp): YYYYMMDD → Date
    - demais campos texto: strip
    """
    int16_cols = ["matriz_filial", "situacao_cadastral", "motivo_situacao", "pais", "municipio"]
    date_cols = ["data_situacao", "data_inicio", "data_situacao_esp"]
    text_cols = [
        "nome_fantasia", "cidade_exterior", "cnae_secundarios",
        "tipo_logradouro", "logradouro", "numero", "complemento",
        "bairro", "uf", "ddd1", "telefone1", "ddd2", "telefone2",
        "ddd_fax", "fax", "situacao_especial",
    ]

    result = df.with_columns([
        pl.col("cnpj_basico").str.strip_chars().str.zfill(8),
        pl.col("cnpj_ordem").str.strip_chars(),
        pl.col("cnpj_dv").str.strip_chars(),
        pl.col("cnae_principal").str.strip_chars().cast(pl.Int32, strict=False),
        pl.col("cep").str.strip_chars().str.replace_all(r"\D", "", literal=False),
        pl.col("email").str.strip_chars().str.to_lowercase(),
        *[pl.col(c).str.strip_chars().cast(pl.Int16, strict=False) for c in int16_cols],
        *[pl.col(c).str.strip_chars() for c in text_cols],
    ])

    for col in date_cols:
        result = result.with_columns(
            pl.col(col)
                .str.strip_chars()
                .str.replace("00000000", "", literal=True)
                .str.strptime(pl.Date, "%Y%m%d", strict=False)
        )

    return result


def transform_socios(df: pl.DataFrame) -> pl.DataFrame:
    """
    Normaliza DataFrame de sócios:
    - cnpj_basico: strip + zfill(8)
    - identificador, qualificacao, qualificacao_repr, pais, faixa_etaria: Int16
    - data_entrada: YYYYMMDD → Date
    - demais strings: strip
    """
    int16_cols = ["identificador", "qualificacao", "qualificacao_repr", "pais", "faixa_etaria"]
    text_cols = ["nome_socio", "cpf_cnpj_socio", "repr_legal", "nome_repr"]

    result = df.with_columns([
        pl.col("cnpj_basico").str.strip_chars().str.zfill(8),
        *[pl.col(c).str.strip_chars().cast(pl.Int16, strict=False) for c in int16_cols],
        *[pl.col(c).str.strip_chars() for c in text_cols],
    ])

    result = result.with_columns(
        pl.col("data_entrada")
            .str.strip_chars()
            .str.replace("00000000", "", literal=True)
            .str.strptime(pl.Date, "%Y%m%d", strict=False)
    )

    return result


def transform_simples(df: pl.DataFrame) -> pl.DataFrame:
    """
    Normaliza DataFrame do Simples Nacional:
    - cnpj_basico: strip + zfill(8)
    - opcao_simples, opcao_mei: strip (char S/N)
    - datas: YYYYMMDD → Date
    """
    date_cols = ["data_opcao_simples", "data_exc_simples", "data_opcao_mei", "data_exc_mei"]

    result = df.with_columns([
        pl.col("cnpj_basico").str.strip_chars().str.zfill(8),
        pl.col("opcao_simples").str.strip_chars(),
        pl.col("opcao_mei").str.strip_chars(),
    ])

    for col in date_cols:
        result = result.with_columns(
            pl.col(col)
                .str.strip_chars()
                .str.replace("00000000", "", literal=True)
                .str.strptime(pl.Date, "%Y%m%d", strict=False)
        )

    return result


def transform_dominios(df: pl.DataFrame) -> pl.DataFrame:
    """
    Normaliza tabelas de domínio (cnaes, municipios, etc.):
    - codigo: strip → Int32
    - descricao: strip
    """
    return df.with_columns([
        pl.col("codigo").str.strip_chars().cast(pl.Int32, strict=False),
        pl.col("descricao").str.strip_chars(),
    ])


# Mapeamento: nome da tabela → função transform
TRANSFORM_MAP: dict[str, callable] = {
    "empresas": transform_empresas,
    "estabelecimentos": transform_estabelecimentos,
    "socios": transform_socios,
    "simples": transform_simples,
    "cnaes": transform_dominios,
    "municipios": transform_dominios,
    "paises": transform_dominios,
    "naturezas": transform_dominios,
    "qualificacoes": transform_dominios,
    "motivos": transform_dominios,
}
