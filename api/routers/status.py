"""Router de status — estatísticas do banco e estado do ETL."""
from fastapi import APIRouter

from database import get_pool

router = APIRouter()


@router.get(
    "/status",
    tags=["status"],
    summary="Status do ETL e estatísticas do banco",
)
async def get_status():
    pool = await get_pool()
    async with pool.acquire() as conn:
        # As três queries não são snapshot-consistent entre si (sem transaction),
        # o que é aceitável para um endpoint de monitoramento.
        total_empresas = await conn.fetchval("SELECT COUNT(*) FROM empresas")
        total_estabelecimentos = await conn.fetchval("SELECT COUNT(*) FROM estabelecimentos")
        etl_states = await conn.fetch(
            "SELECT arquivo, status, loaded_at FROM etl_state ORDER BY loaded_at DESC LIMIT 20"
        )
    return {
        "total_empresas": total_empresas,
        "total_estabelecimentos": total_estabelecimentos,
        "etl_files": [dict(r) for r in etl_states],
    }
