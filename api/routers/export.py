"""Router de exportação — streaming CSV sem carregar tudo na RAM."""
import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from loguru import logger

from database import get_pool
from models.filters import ProspectingFilters
from services.query_builder import build_prospecting_query

router = APIRouter()

_EXPORT_LIMIT = 100_000


@router.get(
    "/export/csv",
    tags=["export"],
    summary="Exportar resultados como CSV (máx. 100.000 linhas)",
    description=(
        "Exporta os registros filtrados em formato CSV com BOM UTF-8 para compatibilidade com Excel. "
        f"O limite máximo de linhas é {_EXPORT_LIMIT:,}, independente do parâmetro `limit` informado. "
        "**Atenção:** em caso de erro do banco de dados após o início do stream, "
        "o cliente receberá um arquivo CSV truncado sem indicação de falha no cabeçalho HTTP "
        "(limitação inerente ao streaming HTTP)."
    ),
)
async def export_csv(filters: ProspectingFilters = Depends()):
    # Força o limite máximo de exportação — ignora o limit do usuário intencionalmente
    filters = filters.model_copy(update={"limit": _EXPORT_LIMIT})
    pool = await get_pool()
    sql, params = build_prospecting_query(filters)

    async def generate():
        buf = io.StringIO()
        writer = None
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    async for row in conn.cursor(sql, *params):
                        if writer is None:
                            writer = csv.DictWriter(buf, fieldnames=row.keys())
                            writer.writeheader()
                            yield buf.getvalue().encode("utf-8-sig")
                            buf.seek(0)
                            buf.truncate()
                        writer.writerow(dict(row))
                        yield buf.getvalue().encode("utf-8-sig")
                        buf.seek(0)
                        buf.truncate()
        except Exception:
            # HTTP 200 já enviado — cliente receberá CSV truncado silenciosamente
            logger.exception("Export stream interrompido por erro no banco de dados")
            raise

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )
