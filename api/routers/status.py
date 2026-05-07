"""Router de status — estatísticas do banco e estado do ETL."""
from fastapi import APIRouter

from database import get_pool

router = APIRouter()

# pg_class.reltuples é uma estimativa mantida pelo VACUUM/ANALYZE — atualiza a cada autovacuum.
# É ordens de grandeza mais rápida que COUNT(*) em tabelas de 50M+ linhas.
_SQL_TABLE_ESTIMATE = "SELECT reltuples::bigint FROM pg_class WHERE relname = $1"

_SQL_ETL_STATE = (
    "SELECT arquivo, status, loaded_at FROM etl_state ORDER BY loaded_at DESC LIMIT 20"
)


@router.get(
    "/status",
    tags=["status"],
    summary="Status do ETL e estatísticas do banco",
)
async def get_status():
    pool = await get_pool()
    async with pool.acquire() as conn:
        total_empresas = await conn.fetchval(_SQL_TABLE_ESTIMATE, "empresas")
        total_estabelecimentos = await conn.fetchval(_SQL_TABLE_ESTIMATE, "estabelecimentos")
        etl_states = await conn.fetch(_SQL_ETL_STATE)
    return {
        "total_empresas": total_empresas,
        "total_estabelecimentos": total_estabelecimentos,
        "etl_files": [dict(r) for r in etl_states],
    }
