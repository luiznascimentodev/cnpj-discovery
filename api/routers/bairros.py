"""Autocomplete de bairros por UF com normalização e desambiguação por município."""
import unicodedata
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from cache import cache_get, cache_set
from database import get_pool

router = APIRouter()

_CACHE_TTL = 3600  # 1h — bairros são dados estáticos
_ACCENTED = "ÁÀÃÂÄÉÈÊËÍÌÎÏÓÒÕÔÖÚÙÛÜÇ"
_UNACCENTED = "AAAAAEEEEIIIIOOOOOUUUUC"
_BAIRRO_CANONICAL_EXPR = """trim(regexp_replace(
        regexp_replace(
            regexp_replace(upper(est.bairro), '^[^A-Z0-9]+', ''),
            '^([A-Z0-9]{1,3}[\\-.:])+', ''
        ),
        '\\s+', ' ', 'g'
    ))"""


class BairroItem(BaseModel):
    bairro: str
    municipio: Optional[int] = None
    municipio_descricao: Optional[str] = None


class MunicipioItem(BaseModel):
    codigo: int
    descricao: str
    total_estabelecimentos: int


# Por cidade, pega o bairro canônico MAIS CURTO que contém o termo buscado.
# Isso elimina variantes longas como "BAIRRO NOVO C SITIO CERCADO" quando
# "SITIO CERCADO" já existe na mesma cidade — o mais curto sempre ganha.
# Depois, desambigua por cidade quando o mesmo nome canônico aparece em > 1 cidade.
_SQL = f"""
WITH normalized AS (
    SELECT
        {_BAIRRO_CANONICAL_EXPR} AS bairro_canonical,
        est.municipio,
        m.descricao AS municipio_descricao,
        COUNT(*)::int AS cnt
    FROM estabelecimentos est
    JOIN municipios m ON m.codigo = est.municipio
    WHERE est.uf = $1
      AND est.bairro IS NOT NULL
      AND est.bairro != ''
      AND {_BAIRRO_CANONICAL_EXPR} ILIKE $2
    GROUP BY 1, 2, 3
),
with_city_count AS (
    SELECT
        bairro_canonical,
        municipio,
        municipio_descricao,
        COUNT(municipio) OVER (PARTITION BY bairro_canonical) AS n_cities
    FROM normalized
)
SELECT DISTINCT
    bairro_canonical                                               AS bairro,
    CASE WHEN n_cities > 1 THEN municipio           ELSE NULL END AS municipio,
    CASE WHEN n_cities > 1 THEN municipio_descricao ELSE NULL END AS municipio_descricao
FROM with_city_count
ORDER BY bairro, municipio_descricao NULLS FIRST
LIMIT 30
"""

_SQL_BY_MUNICIPIO = f"""
SELECT
    {_BAIRRO_CANONICAL_EXPR} AS bairro,
    NULL::int        AS municipio,
    NULL::text       AS municipio_descricao,
    COUNT(*)::int    AS cnt
FROM estabelecimentos est
WHERE est.uf = $1
  AND est.bairro IS NOT NULL
  AND est.bairro != ''
  AND {_BAIRRO_CANONICAL_EXPR} ILIKE $2
  AND est.municipio = $3
GROUP BY 1
ORDER BY cnt DESC, bairro
LIMIT 30
"""

_SQL_MUNICIPIOS = f"""
SELECT
    m.codigo AS codigo,
    m.descricao AS descricao,
    0 AS total_estabelecimentos
FROM municipios m
WHERE translate(upper(m.descricao), '{_ACCENTED}', '{_UNACCENTED}') LIKE $2
  AND $1 IS NOT NULL
ORDER BY m.descricao
LIMIT 30
"""


def _normalize_search(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.upper())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


@router.get("/bairros", tags=["prospecting"], summary="Autocomplete de bairros por UF")
async def list_bairros(
    uf: str = Query(..., min_length=2, max_length=2, description="Sigla do estado (ex: SP)"),
    q: str = Query("", max_length=100, description="Prefixo ou trecho do nome do bairro"),
    municipio: Optional[int] = Query(None, description="Código do município para restringir bairros"),
):
    q = q.strip()
    if len(q) < 2:
        return []

    uf_upper = uf.upper()
    cache_key = f"cnpj:bairros:v2:{uf_upper}:{municipio or 'all'}:{q.lower()}"

    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    pool = await get_pool()
    async with pool.acquire() as conn:
        if municipio is None:
            rows = await conn.fetch(_SQL, uf_upper, f"%{q}%")
        else:
            rows = await conn.fetch(_SQL_BY_MUNICIPIO, uf_upper, f"%{q}%", municipio)

    result = [
        BairroItem(
            bairro=r["bairro"],
            municipio=r["municipio"],
            municipio_descricao=r["municipio_descricao"],
        ).model_dump()
        for r in rows
    ]
    await cache_set(cache_key, result, ttl=_CACHE_TTL)
    return result


@router.get("/municipios", tags=["prospecting"], summary="Autocomplete de municípios por UF")
async def list_municipios(
    uf: str = Query(..., min_length=2, max_length=2, description="Sigla do estado (ex: SP)"),
    q: str = Query("", max_length=100, description="Prefixo ou trecho do nome do município"),
):
    q = q.strip()
    if len(q) < 2:
        return []

    uf_upper = uf.upper()
    cache_key = f"cnpj:municipios:v2:{uf_upper}:{q.lower()}"

    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL_MUNICIPIOS, uf_upper, f"%{_normalize_search(q)}%")

    result = [
        MunicipioItem(
            codigo=r["codigo"],
            descricao=r["descricao"],
            total_estabelecimentos=r["total_estabelecimentos"],
        ).model_dump()
        for r in rows
    ]
    await cache_set(cache_key, result, ttl=_CACHE_TTL)
    return result
