"""Router de prospecção — busca de empresas com filtros avançados."""
from fastapi import APIRouter, Depends

from database import get_pool
from models.filters import ProspectingFilters
from models.empresa import EmpresaOut
from services.query_builder import build_prospecting_query

router = APIRouter()


@router.get(
    "/prospecting",
    response_model=list[EmpresaOut],
    tags=["prospecting"],
    summary="Buscar empresas com filtros avançados",
)
async def search_empresas(filters: ProspectingFilters = Depends()):
    pool = await get_pool()
    sql, params = build_prospecting_query(filters)
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]
