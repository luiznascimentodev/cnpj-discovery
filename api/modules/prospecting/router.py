"""Router de prospecção — busca de empresas com filtros avançados."""
import random

from fastapi import APIRouter, Depends

from core.cache import cache_get, cache_set, make_cache_key
from core.db import get_pool
from core.dependencies import prospecting_filters_dependency
from modules.prospecting.schemas import ProspectingFilters
from modules.empresa import EmpresaOut
from modules.prospecting.service import build_prospecting_query

router = APIRouter()

_CACHE_TTL = 300  # 5 minutos — dados do RF mudam mensalmente

# Tamanho do "pool" buscado quando a primeira página é embaralhada.
# Multiplicamos o limit do usuário e capamos para não explodir queries amplas.
# O pool é cacheado por filtros — a aleatoriedade vem do shuffle em memória, então
# usuários diferentes (e cliques sucessivos do mesmo usuário) recebem ordens distintas
# mesmo aproveitando o mesmo cache.
_RANDOMIZE_POOL_MULTIPLIER = 20
_RANDOMIZE_POOL_CAP = 1000


def _sort_demais_last(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: row.get("porte") == 5)


def _shuffle_preserving_demais_last(rows: list[dict], rng: random.Random) -> list[dict]:
    """Embaralha não-demais e demais separadamente, mantendo demais no final."""
    non_demais = [r for r in rows if r.get("porte") != 5]
    demais = [r for r in rows if r.get("porte") == 5]
    rng.shuffle(non_demais)
    rng.shuffle(demais)
    return non_demais + demais


def _should_randomize(filters: ProspectingFilters) -> bool:
    """Sem cursor, sem CNPJ direto e em busca larga: vale embaralhar a primeira página."""
    if filters.cnpj is not None:
        return False
    if filters.cursor_cnpj_basico and filters.cursor_cnpj_ordem:
        return False
    return True


@router.get(
    "/prospecting",
    response_model=list[EmpresaOut],
    tags=["prospecting"],
    summary="Buscar empresas com filtros avançados",
)
async def search_empresas(filters: ProspectingFilters = Depends(prospecting_filters_dependency)):
    randomize = _should_randomize(filters)

    if randomize:
        pool_limit = min(filters.limit * _RANDOMIZE_POOL_MULTIPLIER, _RANDOMIZE_POOL_CAP)
        fetch_filters = filters.model_copy(update={"limit": max(pool_limit, filters.limit)})
    else:
        fetch_filters = filters

    cache_key = make_cache_key("prospecting", fetch_filters.model_dump())
    cached = await cache_get(cache_key)

    if cached is None:
        pool = await get_pool()
        sql, params = build_prospecting_query(fetch_filters)
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        cached = _sort_demais_last([dict(r) for r in rows])
        await cache_set(cache_key, cached, ttl=_CACHE_TTL)

    if randomize:
        # Nova ordem a cada requisição: evita concentrar tráfego de prospecção
        # nas mesmas empresas (que estariam sempre no topo do índice lexicográfico).
        shuffled = _shuffle_preserving_demais_last(list(cached), random.Random())
        return shuffled[: filters.limit]

    return cached
