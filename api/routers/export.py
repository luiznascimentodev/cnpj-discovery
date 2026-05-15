"""Router de exportação — streaming CSV sem carregar tudo na RAM."""
import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from loguru import logger

from core.db import get_pool
from core.dependencies import export_filters_dependency
from models.filters import ProspectingFilters
from services.query_builder import build_prospecting_query

router = APIRouter()

_BATCH_ROWS = 1_000  # número de linhas acumuladas antes de cada yield


@router.get(
    "/export/csv",
    tags=["export"],
    summary="Exportar todos os resultados filtrados como CSV",
    description=(
        "Exporta os registros filtrados em formato CSV com BOM UTF-8 para compatibilidade com Excel. "
        "Exporta todos os registros que correspondem aos filtros informados; `limit` e cursor são ignorados. "
        "**Atenção:** em caso de erro do banco de dados após o início do stream, "
        "o cliente receberá um arquivo CSV truncado sem indicação de falha no cabeçalho HTTP "
        "(limitação inerente ao streaming HTTP)."
    ),
)
async def export_csv(filters: ProspectingFilters = Depends(export_filters_dependency)):
    pool = await get_pool()
    sql, params = build_prospecting_query(filters, include_limit=False)

    async def generate():
        buf = io.StringIO()
        writer = None
        pending: list[dict] = []

        def flush_pending() -> bytes:
            for row_dict in pending:
                writer.writerow(row_dict)
            pending.clear()
            out = buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate()
            return out

        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    async for row in conn.cursor(sql, *params):
                        row_dict = dict(row)
                        if writer is None:
                            writer = csv.DictWriter(buf, fieldnames=row_dict.keys())
                            writer.writeheader()
                            yield buf.getvalue().encode("utf-8-sig")
                            buf.seek(0)
                            buf.truncate()
                        pending.append(row_dict)
                        if len(pending) >= _BATCH_ROWS:
                            yield flush_pending()

            # Flush remaining rows after cursor exhausted
            if writer is not None and pending:
                yield flush_pending()

        except Exception:
            logger.exception("Export stream interrompido por erro no banco de dados")
            raise  # pragma: no cover

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )
