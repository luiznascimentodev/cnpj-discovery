"""Router de catálogo de CNAEs agrupados por segmento."""
from fastapi import APIRouter

from cache import cache_get, cache_set
from database import get_pool
from services.cnae_segments import group_cnaes

router = APIRouter()

_CACHE_KEY = "cnpj:cnaes:all"
_CACHE_TTL = 86400  # 24h

_SQL = "SELECT codigo, descricao FROM cnaes ORDER BY codigo"


@router.get("/cnaes", tags=["cnaes"], summary="Lista todos os CNAEs agrupados por segmento")
async def list_cnaes():
    cached = await cache_get(_CACHE_KEY)
    if cached is not None:
        return cached

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL)

    cnaes = [{"codigo": r["codigo"], "descricao": r["descricao"]} for r in rows]
    result = {"segments": group_cnaes(cnaes)}
    await cache_set(_CACHE_KEY, result, ttl=_CACHE_TTL)
    return result
