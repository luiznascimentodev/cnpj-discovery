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

    if not randomize:
        # Caminho legado: busca direta por CNPJ ou paginação por cursor.
        # Mantém ordem determinística pra o cursor funcionar consistentemente.
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

    # Primeira página randomizada: traz empresas JÁ enriquecidas primeiro
    # (contato disponível imediato) e depois as ainda-não-enriquecidas, com
    # ordem aleatória dentro de cada bloco. Cache compartilhado entre usuários,
    # aleatoriedade é o shuffle em memória.
    pool_limit = min(filters.limit * _RANDOMIZE_POOL_MULTIPLIER, _RANDOMIZE_POOL_CAP)
    fetch_filters = filters.model_copy(update={"limit": max(pool_limit, filters.limit)})

    # Prefixo v2 invalida cache antigo cujo formato era lista plana.
    cache_key = make_cache_key("prospecting_v2", fetch_filters.model_dump())
    cached = await cache_get(cache_key)

    if cached is None:
        pool = await get_pool()
        sql_enriched, params_enriched = build_prospecting_query(
            fetch_filters, enriched_filter=True
        )
        sql_other, params_other = build_prospecting_query(
            fetch_filters, enriched_filter=False
        )
        async with pool.acquire() as conn:
            rows_enriched = await conn.fetch(sql_enriched, *params_enriched)
            rows_other = await conn.fetch(sql_other, *params_other)
        cached = {
            "enriched": _sort_demais_last([dict(r) for r in rows_enriched]),
            "non_enriched": _sort_demais_last([dict(r) for r in rows_other]),
        }
        await cache_set(cache_key, cached, ttl=_CACHE_TTL)

    rng = random.Random()
    enriched = _shuffle_preserving_demais_last(list(cached["enriched"]), rng)
    non_enriched = _shuffle_preserving_demais_last(list(cached["non_enriched"]), rng)
    # Dedup defensivo: as duas consultas têm EXISTS / NOT EXISTS mutuamente
    # exclusivos, então em produção não há overlap. Esse seen-set blinda contra
    # mocks de teste e qualquer regressão silenciosa na SQL.
    seen: set[tuple[str, str, str]] = set()
    merged: list[dict] = []
    for row in enriched + non_enriched:
        key = (row["cnpj_basico"], row["cnpj_ordem"], row["cnpj_dv"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged[: filters.limit]
