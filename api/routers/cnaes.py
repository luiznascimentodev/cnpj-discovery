"""Router de catálogo de CNAEs para seleção manual e por assunto."""
from fastapi import APIRouter

from core.cache import cache_get, cache_set
from core.db import get_pool
from services.cnae_segments import build_cnae_catalog

router = APIRouter()

_CACHE_KEY = "cnpj:cnaes:catalog:v2"
_CACHE_TTL = 86400  # 24h

_SQL = "SELECT codigo, descricao FROM cnaes ORDER BY codigo"


@router.get("/cnaes", tags=["cnaes"], summary="Lista todos os CNAEs e agrupamentos por assunto")
async def list_cnaes():
    cached = await cache_get(_CACHE_KEY)
    if cached is not None:
        return cached

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL)

    cnaes = [{"codigo": r["codigo"], "descricao": r["descricao"]} for r in rows]
    result = build_cnae_catalog(cnaes)
    await cache_set(_CACHE_KEY, result, ttl=_CACHE_TTL)
    return result
