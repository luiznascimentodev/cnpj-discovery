"""Autocomplete de municipios e bairros normalizados para prospeccao."""
import unicodedata
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from core.cache import cache_get, cache_set
from core.db import get_pool

router = APIRouter()

_CACHE_TTL = 3600  # 1h — bairros são dados estáticos
_ACCENTED = "ÁÀÃÂÄÉÈÊËÍÌÎÏÓÒÕÔÖÚÙÛÜÇ"
_UNACCENTED = "AAAAAEEEEIIIIOOOOOUUUUC"

class BairroItem(BaseModel):
    bairro: str
    municipio: Optional[int] = None
    municipio_descricao: Optional[str] = None


class MunicipioItem(BaseModel):
    codigo: int
    descricao: str
    total_estabelecimentos: int


_SQL_BY_MUNICIPIO = f"""
SELECT
    bairro_canonical AS bairro,
    NULL::int        AS municipio,
    NULL::text       AS municipio_descricao,
    SUM(cnt)::int    AS cnt
FROM bairros_lookup
WHERE uf = $1
  AND municipio = $3
  AND bairro_canonical ILIKE $2
GROUP BY bairro_canonical
ORDER BY cnt DESC, bairro
LIMIT 30
"""

_SQL_MUNICIPIOS = f"""
SELECT
    municipio AS codigo,
    municipio_descricao AS descricao,
    SUM(cnt)::int AS total_estabelecimentos
FROM bairros_lookup
WHERE uf = $1
  AND translate(upper(municipio_descricao), '{_ACCENTED}', '{_UNACCENTED}') LIKE $2
GROUP BY municipio, municipio_descricao
ORDER BY total_estabelecimentos DESC, municipio_descricao
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
    if municipio is None or len(q) < 2:
        return []

    uf_upper = uf.upper()
    cache_key = f"cnpj:bairros:v2:{uf_upper}:{municipio or 'all'}:{q.lower()}"

    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    pool = await get_pool()
    async with pool.acquire() as conn:
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
