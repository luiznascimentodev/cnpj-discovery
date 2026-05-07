"""Autocomplete de bairros por UF com normalização e desambiguação por município."""
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from cache import cache_get, cache_set
from database import get_pool

router = APIRouter()

_CACHE_TTL = 3600  # 1h — bairros são dados estáticos


class BairroItem(BaseModel):
    bairro: str
    municipio: Optional[int] = None
    municipio_descricao: Optional[str] = None


# Por cidade, pega o bairro canônico MAIS CURTO que contém o termo buscado.
# Isso elimina variantes longas como "BAIRRO NOVO C SITIO CERCADO" quando
# "SITIO CERCADO" já existe na mesma cidade — o mais curto sempre ganha.
# Depois, desambigua por cidade quando o mesmo nome canônico aparece em > 1 cidade.
_SQL = """
WITH matches AS (
    SELECT
        bairro_canonical,
        municipio,
        municipio_descricao,
        length(bairro_canonical) AS len
    FROM bairros_lookup
    WHERE uf = $1 AND bairro_canonical ILIKE $2
),
-- Per city: keep only the shortest canonical that contains the search term.
shortest_per_city AS (
    SELECT DISTINCT ON (municipio)
        bairro_canonical,
        municipio,
        municipio_descricao,
        len
    FROM matches
    ORDER BY municipio, len, bairro_canonical
),
-- Distinct shortest forms seen globally (the "leaders").
global_leaders AS (
    SELECT DISTINCT bairro_canonical, len
    FROM shortest_per_city
),
-- Suffix-collapse: if a per-city bairro ENDS WITH a shorter global leader
-- (e.g. "BAIRRO NOVO C SITIO CERCADO" → "SITIO CERCADO"), re-label it.
normalized AS (
    SELECT
        COALESCE(
            (SELECT gl.bairro_canonical
             FROM global_leaders gl
             WHERE s.bairro_canonical LIKE '%' || gl.bairro_canonical
               AND s.bairro_canonical <> gl.bairro_canonical
             ORDER BY gl.len
             LIMIT 1),
            s.bairro_canonical
        ) AS bairro_canonical,
        s.municipio,
        s.municipio_descricao
    FROM shortest_per_city s
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


@router.get("/bairros", tags=["prospecting"], summary="Autocomplete de bairros por UF")
async def list_bairros(
    uf: str = Query(..., min_length=2, max_length=2, description="Sigla do estado (ex: SP)"),
    q: str = Query("", max_length=100, description="Prefixo ou trecho do nome do bairro"),
):
    q = q.strip()
    if len(q) < 2:
        return []

    uf_upper = uf.upper()
    cache_key = f"cnpj:bairros:{uf_upper}:{q.lower()}"

    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL, uf_upper, f"%{q}%")

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
