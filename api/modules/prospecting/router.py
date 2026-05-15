"""Router de prospecção — busca de empresas com filtros avançados."""
from fastapi import APIRouter, Depends

from core.cache import cache_get, cache_set, make_cache_key
from core.db import get_pool
from core.dependencies import prospecting_filters_dependency
from modules.prospecting.schemas import ProspectingFilters
from modules.empresa import EmpresaOut
from modules.prospecting.service import build_prospecting_query

router = APIRouter()

_CACHE_TTL = 300  # 5 minutos — dados do RF mudam mensalmente


def _sort_demais_last(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: row.get("porte") == 5)


@router.get(
    "/prospecting",
    response_model=list[EmpresaOut],
    tags=["prospecting"],
    summary="Buscar empresas com filtros avançados",
)
async def search_empresas(filters: ProspectingFilters = Depends(prospecting_filters_dependency)):
    cache_key = make_cache_key("prospecting", filters.model_dump())

    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    pool = await get_pool()
    sql, params = build_prospecting_query(filters)
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)

    result = _sort_demais_last([dict(r) for r in rows])
    await cache_set(cache_key, result, ttl=_CACHE_TTL)
    return result
